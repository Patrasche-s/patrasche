"""Unit tests for batch summarizer (Gemini mock)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

from summarizer import (  # noqa: E402
    DEFAULT_GEMINI_MODEL,
    _append_link_line,
    _parse_batch_response,
    _strip_json_fence,
    _summarize_batch_with_client,
    summarize_news_list,
)


def _sample_items(count: int = 3) -> list[dict[str, str]]:
    return [
        {
            "category": "IT/테크",
            "title": f"Title {i}",
            "link": f"https://example.com/news/{i}",
            "rss_description": f"Description {i}",
        }
        for i in range(count)
    ]


def _batch_json_payload(items: list[dict[str, str]]) -> str:
    return json.dumps(
        {
            "summaries": [
                {
                    "index": i,
                    "summary": (
                        f"[오늘의 한 줄]: 한 줄 {i}\n\n"
                        f"[주요 내용]:\n- bullet A {i}\n- bullet B {i}"
                    ),
                }
                for i in range(len(items))
            ]
        },
        ensure_ascii=False,
    )


def test_batch_calls_generate_content_once_for_three_items() -> None:
    items = _sample_items(3)
    mock_client = MagicMock()
    mock_client.generate_content.return_value = SimpleNamespace(
        text=_batch_json_payload(items)
    )

    result = _summarize_batch_with_client(mock_client, items, timeout_seconds=None)

    assert mock_client.generate_content.call_count == 1
    assert len(result) == 3
    for i, summary in enumerate(result):
        assert summary.endswith(f"🔗 원문 보기: https://example.com/news/{i}")


def test_summarize_news_list_uses_single_gemini_call() -> None:
    items = _sample_items(3)
    mock_client = MagicMock()
    mock_client.generate_content.return_value = SimpleNamespace(
        text=_batch_json_payload(items)
    )

    with patch("summarizer._require_api_key", return_value="test-key"):
        with patch("google.generativeai.configure"):
            with patch("google.generativeai.GenerativeModel", return_value=mock_client):
                summaries = summarize_news_list(items)

    assert mock_client.generate_content.call_count == 1
    assert len(summaries) == 3


def test_summarize_news_list_uses_flash_lite_default_model() -> None:
    items = _sample_items(1)
    mock_client = MagicMock()
    mock_client.generate_content.return_value = SimpleNamespace(
        text=_batch_json_payload(items)
    )

    with patch("summarizer._require_api_key", return_value="test-key"):
        with patch("google.generativeai.configure"):
            with patch("google.generativeai.GenerativeModel", return_value=mock_client) as model_cls:
                summarize_news_list(items)

    model_cls.assert_called_once_with(DEFAULT_GEMINI_MODEL)


def test_parse_batch_response_appends_link_line() -> None:
    items = _sample_items(1)
    raw = _batch_json_payload(items)
    summaries = _parse_batch_response(raw, items)
    assert summaries[0].endswith("🔗 원문 보기: https://example.com/news/0")
    assert "[오늘의 한 줄]" in summaries[0]


def test_strip_json_fence_parses_markdown_wrapped_json() -> None:
    items = _sample_items(2)
    raw = "```json\n" + _batch_json_payload(items) + "\n```"
    stripped = _strip_json_fence(raw)
    summaries = _parse_batch_response(stripped, items)
    assert len(summaries) == 2


def test_append_link_line_replaces_existing_link_suffix() -> None:
    text = "[오늘의 한 줄]: test\n\n🔗 원문 보기: old"
    out = _append_link_line(text, "https://example.com/new")
    assert out.endswith("🔗 원문 보기: https://example.com/new")
    assert "old" not in out


def test_parse_batch_response_fails_on_invalid_json() -> None:
    items = _sample_items(1)
    with pytest.raises(RuntimeError, match="JSON 파싱"):
        _parse_batch_response("not-json", items)


def test_parse_batch_response_fails_on_missing_index() -> None:
    items = _sample_items(2)
    raw = json.dumps(
        {
            "summaries": [
                {"index": 0, "summary": "ok"},
            ]
        }
    )
    with pytest.raises(RuntimeError, match="개수 불일치|index"):
        _parse_batch_response(raw, items)


def test_parse_batch_response_fails_on_duplicate_index() -> None:
    items = _sample_items(2)
    raw = json.dumps(
        {
            "summaries": [
                {"index": 0, "summary": "a"},
                {"index": 0, "summary": "b"},
            ]
        }
    )
    with pytest.raises(RuntimeError, match="중복"):
        _parse_batch_response(raw, items)


def test_parse_batch_response_fails_on_non_string_summary() -> None:
    items = _sample_items(1)
    raw = json.dumps({"summaries": [{"index": 0, "summary": 123}]})
    with pytest.raises(RuntimeError, match="문자열"):
        _parse_batch_response(raw, items)


def test_batch_fail_single_fallback_partial_success() -> None:
    items = _sample_items(3)
    mock_client = MagicMock()
    call_count = 0

    def side_effect(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return SimpleNamespace(text="not-json")
        if call_count == 3:
            raise RuntimeError("single fail")
        item_idx = 0 if call_count == 2 else 2
        return SimpleNamespace(text=_batch_json_payload([items[item_idx]]))

    mock_client.generate_content.side_effect = side_effect

    with patch("summarizer._require_api_key", return_value="test-key"):
        with patch("google.generativeai.configure"):
            with patch("google.generativeai.GenerativeModel", return_value=mock_client):
                result = summarize_news_list(items)

    assert len(result) == 3
    assert result[0] is not None
    assert result[1] is None
    assert result[2] is not None
    assert mock_client.generate_content.call_count == 4


def test_batch_fail_all_single_fail_raises() -> None:
    items = _sample_items(2)
    mock_client = MagicMock()
    mock_client.generate_content.side_effect = [
        SimpleNamespace(text="not-json"),
        RuntimeError("single fail 0"),
        RuntimeError("single fail 1"),
    ]

    with patch("summarizer._require_api_key", return_value="test-key"):
        with patch("google.generativeai.configure"):
            with patch("google.generativeai.GenerativeModel", return_value=mock_client):
                with pytest.raises(RuntimeError, match="single fail 1"):
                    summarize_news_list(items)

    assert mock_client.generate_content.call_count == 3
