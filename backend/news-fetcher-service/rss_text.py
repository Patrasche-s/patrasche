"""RSS description extraction and HTML cleanup."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def strip_html_tags(raw: str) -> str:
    """Remove HTML tags from RSS description text."""
    text = (raw or "").strip()
    if not text:
        return ""
    if "<" not in text:
        return text
    parser = _HTMLTextExtractor()
    parser.feed(text)
    parser.close()
    return parser.get_text()


def extract_rss_description(entry: Any) -> str:
    """Try summary then description fields from a feedparser entry."""
    for key in ("summary", "description"):
        raw = entry.get(key)
        if raw is None:
            continue
        cleaned = strip_html_tags(str(raw))
        if cleaned:
            return cleaned
    return ""


def extract_pub_date_utc(entry: Any) -> str:
    published = entry.get("published") or entry.get("updated") or ""
    return str(published).strip()


MIN_RSS_DESCRIPTION_LEN = 40

_LIVE_LIKE_TITLE_KEYWORDS = (
    "minute-by-minute",
    "as it happened",
    "latest updates",
    "live updates",
)


def should_skip_article(title: str, link: str, description: str = "") -> tuple[bool, str | None]:
    """
    요약기에 부적합한 RSS 항목(live blog, 짧은 description 등)인지 판별한다.

    Returns:
        (skip, reason) — skip=True면 수집에서 제외. reason은 로그용 코드.
    """
    title_l = (title or "").lower()
    link_l = (link or "").lower()
    desc = (description or "").strip()

    if "/live/" in link_l:
        return True, "live_article_url"

    if any(keyword in title_l for keyword in _LIVE_LIKE_TITLE_KEYWORDS):
        return True, "live_like_title"

    if not desc or len(desc) < MIN_RSS_DESCRIPTION_LEN:
        return True, "too_short_description"

    return False, None


def extract_author(entry: Any) -> str:
    author = entry.get("author") or ""
    if author:
        return str(author).strip()
    authors = entry.get("authors") or []
    if authors and isinstance(authors, list):
        first = authors[0]
        if isinstance(first, dict):
            return str(first.get("name") or first.get("email") or "").strip()
        return str(first).strip()
    return ""
