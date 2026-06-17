"""Unit tests for RSS text helpers."""

from __future__ import annotations

from rss_text import extract_rss_description, should_skip_article, strip_html_tags

LONG_DESC = "A" * 40


def test_strip_html_tags_removes_tags() -> None:
    raw = "<p>Hello <b>world</b></p>"
    assert strip_html_tags(raw) == "Hello world"


def test_extract_rss_description_prefers_summary() -> None:
    entry = {"summary": "<p>First summary</p>", "description": "Second"}
    assert extract_rss_description(entry) == "First summary"


def test_extract_rss_description_falls_back_to_description() -> None:
    entry = {"description": "Plain description"}
    assert extract_rss_description(entry) == "Plain description"


def test_should_skip_live_article_url() -> None:
    skip, reason = should_skip_article(
        "Austria v Jordan live",
        "https://www.theguardian.com/football/live/2026/jun/17/austria-jordan",
        LONG_DESC,
    )
    assert skip is True
    assert reason == "live_article_url"


def test_should_not_skip_normal_sports_report() -> None:
    skip, reason = should_skip_article(
        "Harry Kane says American dream is real",
        "https://www.theguardian.com/football/2026/jun/17/harry-kane-american-dream",
        LONG_DESC,
    )
    assert skip is False
    assert reason is None


def test_should_not_skip_title_containing_live_as_word() -> None:
    skip, reason = should_skip_article(
        "How football fans live with World Cup fever",
        "https://www.theguardian.com/football/2026/jun/17/world-cup-fever",
        LONG_DESC,
    )
    assert skip is False
    assert reason is None


def test_should_skip_live_like_title() -> None:
    skip, reason = should_skip_article(
        "Argentina v Algeria – as it happened",
        "https://www.theguardian.com/football/2026/jun/16/argentina-algeria",
        LONG_DESC,
    )
    assert skip is True
    assert reason == "live_like_title"


def test_should_skip_too_short_description() -> None:
    skip, reason = should_skip_article(
        "Match report headline",
        "https://www.theguardian.com/football/2026/jun/16/report",
        "Too short",
    )
    assert skip is True
    assert reason == "too_short_description"

