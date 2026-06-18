"""CI smoke tests for news-fetcher-service (lifespan + AsyncIOScheduler).

Ports: User 8000, Mail 8002, Fetcher 8003, Summarizer 8004.
테스트에서는 ENABLE_SCHEDULER=false 로 크론·외부 API 호출을 막습니다.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

_SERVICE_DIR = Path(__file__).resolve().parents[1]

# import 전에 고정 — lifespan에서 스케줄러가 기동되지 않도록 함
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ.setdefault("SUMMARIZER_URL", "http://localhost:8004/summarize")
os.environ.setdefault("NEWS_STORE_BASE_URL", "http://localhost:8004")

sys.path.insert(0, str(_SERVICE_DIR))

import main as fetcher_main  # noqa: E402

app = fetcher_main.app


@pytest.fixture(scope="session", autouse=True)
def _disable_scheduler_for_tests() -> Iterator[None]:
    """세션 전체에서 스케줄러 비활성화 및 종료 후 잔여 리소스 정리."""
    os.environ["ENABLE_SCHEDULER"] = "false"
    yield
    if fetcher_main.scheduler.running:
        fetcher_main.scheduler.shutdown(wait=False)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """with TestClient(app) 로 lifespan startup/shutdown 이 한 쌍으로 실행되게 함."""
    assert fetcher_main._env_bool("ENABLE_SCHEDULER", True) is False
    with TestClient(app) as test_client:
        assert fetcher_main.scheduler.running is False
        yield test_client
    assert fetcher_main.scheduler.running is False


def test_health_returns_200_json_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_lifespan_does_not_start_scheduler() -> None:
    """lifespan 진입·종료 후에도 스케줄러가 켜지지 않아야 함 (K8s/CI 안전)."""
    with TestClient(app) as test_client:
        assert test_client.get("/health").status_code == 200
        assert fetcher_main.scheduler.running is False
    assert fetcher_main.scheduler.running is False


def test_run_pipeline_saves_partial_summaries(monkeypatch: pytest.MonkeyPatch) -> None:
    category = "경제"
    items = [
        {
            "title": "T0",
            "link": "https://example.com/0",
            "category": category,
            "rss_description": "d0",
        },
        {
            "title": "T1",
            "link": "https://example.com/1",
            "category": category,
            "rss_description": "d1",
        },
        {
            "title": "T2",
            "link": "https://example.com/2",
            "category": category,
            "rss_description": "d2",
        },
    ]

    monkeypatch.setattr(
        fetcher_main,
        "fetch_latest_news_all_categories",
        lambda limit, max_scan: {category: items},
    )
    monkeypatch.setattr(fetcher_main, "upload_rss_snapshot", lambda *args, **kwargs: "s3/key")
    monkeypatch.setattr(fetcher_main, "_http_get_existing_links", lambda client, links: set())

    saved_links: list[str] = []

    def mock_post_news(client, body):
        saved_links.append(body["link"])
        return True

    monkeypatch.setattr(fetcher_main, "_http_post_news", mock_post_news)

    def mock_summarize(client, url, payload, **kwargs):
        return {"summaries": ["summary0", None, "summary2"]}

    monkeypatch.setattr(fetcher_main, "_post_summarize_with_retries", mock_summarize)

    stats = fetcher_main.run_pipeline(summarizer_http_max_extra_tries=0)

    assert stats["saved"] == 2
    assert stats["failed"] == 1
    assert stats["summarized"] == 2
    assert saved_links == ["https://example.com/0", "https://example.com/2"]


def test_select_fresh_items_fills_limit_after_existing_links() -> None:
    items = [
        {"title": f"T{i}", "link": f"https://example.com/{i}", "category": "경제"}
        for i in range(5)
    ]

    fresh_items, already_saved, shortfall = fetcher_main._select_fresh_items(
        items,
        {"https://example.com/0", "https://example.com/2"},
        limit=3,
    )

    assert [item["link"] for item in fresh_items] == [
        "https://example.com/1",
        "https://example.com/3",
        "https://example.com/4",
    ]
    assert already_saved == 2
    assert shortfall == 0


def test_select_fresh_items_reports_shortfall() -> None:
    items = [
        {"title": "Old 0", "link": "https://example.com/old-0", "category": "연예"},
        {"title": "Old 1", "link": "https://example.com/old-1", "category": "연예"},
        {"title": "New", "link": "https://example.com/new", "category": "연예"},
    ]

    fresh_items, already_saved, shortfall = fetcher_main._select_fresh_items(
        items,
        {"https://example.com/old-0", "https://example.com/old-1"},
        limit=3,
    )

    assert [item["link"] for item in fresh_items] == ["https://example.com/new"]
    assert already_saved == 2
    assert shortfall == 2


def test_run_pipeline_fetches_rss_candidates_up_to_scan_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, int] = {}

    def mock_fetch_latest_news_all_categories(limit: int, max_scan: int):
        seen["limit"] = limit
        seen["max_scan"] = max_scan
        return {}

    monkeypatch.setattr(
        fetcher_main,
        "fetch_latest_news_all_categories",
        mock_fetch_latest_news_all_categories,
    )

    stats = fetcher_main.run_pipeline(per_category_limit=3, summarizer_http_max_extra_tries=0)

    assert seen == {"limit": fetcher_main.DEFAULT_MAX_RSS_SCAN, "max_scan": fetcher_main.DEFAULT_MAX_RSS_SCAN}
    assert stats["to_summarize"] == 0


def test_post_summarize_retries_once_after_502(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(502, text="temporary bad gateway", request=request)
        return httpx.Response(200, json={"summaries": ["ok"]}, request=request)

    monkeypatch.setattr(fetcher_main.time, "sleep", lambda seconds: None)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        body = fetcher_main._post_summarize_with_retries(
            client,
            "http://summarizer.test/summarize",
            {"items": [{"title": "T"}]},
            category="경제",
            item_count=1,
            max_extra_tries=1,
        )

    assert body == {"summaries": ["ok"]}
    assert calls == 2
