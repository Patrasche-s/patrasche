"""Unit tests for RSS fetch filtering."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fetcher import SPORTS_CATEGORY, fetch_latest_news

LONG_DESC = "A" * 40


def _entry(title: str, link: str, description: str = LONG_DESC) -> dict:
    return {
        "title": title,
        "link": link,
        "summary": description,
    }


@patch("fetcher.feedparser.parse")
def test_sports_skips_live_and_fills_from_next_entries(mock_parse: MagicMock) -> None:
    mock_parse.return_value = MagicMock(
        entries=[
            _entry(
                "Austria v Jordan live",
                "https://www.theguardian.com/football/live/2026/jun/17/austria-jordan",
            ),
            _entry(
                "Harry Kane says American dream is real",
                "https://www.theguardian.com/football/2026/jun/17/harry-kane",
            ),
            _entry(
                "Argentina beat Algeria in group J",
                "https://www.theguardian.com/football/2026/jun/16/argentina-algeria-report",
            ),
            _entry(
                "Coach criticises referee after defeat",
                "https://www.theguardian.com/football/2026/jun/16/coach-referee",
            ),
        ]
    )

    items = fetch_latest_news(SPORTS_CATEGORY, limit=3)

    assert len(items) == 3
    assert all("/live/" not in item["link"] for item in items)
    assert items[0]["title"].startswith("Harry Kane")


@patch("fetcher.feedparser.parse")
def test_non_sports_category_does_not_apply_skip_filter(mock_parse: MagicMock) -> None:
    mock_parse.return_value = MagicMock(
        entries=[
            _entry(
                "Tech headline live blog style",
                "https://example.com/tech/live/story",
                "short",
            ),
        ]
    )

    items = fetch_latest_news("IT/테크", limit=1)

    assert len(items) == 1
    assert "/live/" in items[0]["link"]


@patch("fetcher.feedparser.parse")
def test_sports_respects_max_scan(mock_parse: MagicMock) -> None:
    mock_parse.return_value = MagicMock(
        entries=[
            _entry(
                f"Live {i}",
                f"https://www.theguardian.com/football/live/2026/jun/17/match-{i}",
            )
            for i in range(5)
        ]
        + [
            _entry(
                "Valid report",
                "https://www.theguardian.com/football/2026/jun/16/report",
            ),
        ]
    )

    items = fetch_latest_news(SPORTS_CATEGORY, limit=1, max_scan=3)

    assert items == []
