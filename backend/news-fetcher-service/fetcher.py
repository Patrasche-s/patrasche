from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import feedparser

from rss_text import (
    extract_author,
    extract_pub_date_utc,
    extract_rss_description,
    should_skip_article,
)

log = logging.getLogger("news-fetcher")

RSS_FEEDS: Dict[str, str] = {
    "IT/테크": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "경제": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "국제": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "스포츠": "https://www.theguardian.com/uk/sport/rss",
    "연예": "https://rss.nytimes.com/services/xml/rss/nyt/Movies.xml",
    "정치": "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
}

CATEGORY_SLUGS: Dict[str, str] = {
    "IT/테크": "it-tech",
    "경제": "economy",
    "국제": "world",
    "스포츠": "sports",
    "연예": "entertainment",
    "정치": "politics",
}

DEFAULT_NEWS_LIMIT = 3
DEFAULT_MAX_RSS_SCAN = 20
SPORTS_CATEGORY = "스포츠"


def get_rss_url(category: str) -> str:
    """카테고리에 해당하는 RSS URL을 반환한다."""
    if category not in RSS_FEEDS:
        available = ", ".join(RSS_FEEDS.keys())
        raise ValueError(f"지원하지 않는 카테고리입니다: {category} (지원: {available})")
    return RSS_FEEDS[category]


def fetch_latest_news(
    category: str,
    *,
    limit: int = DEFAULT_NEWS_LIMIT,
    max_scan: int = DEFAULT_MAX_RSS_SCAN,
) -> List[Dict[str, str]]:
    """
    지정한 카테고리의 최신 뉴스 최대 limit건(제목/링크/description 등)을 리스트로 가져온다.
    스포츠(Guardian)는 live·짧은 description 등 비정형 RSS 항목을 건너뛰고 다음 항목으로 채운다.
    피드에 글이 없으면 빈 리스트를 반환한다.
    """
    if limit < 1:
        raise ValueError("limit은 1 이상이어야 합니다.")
    if max_scan < 1:
        raise ValueError("max_scan은 1 이상이어야 합니다.")

    rss_url = get_rss_url(category)
    feed = feedparser.parse(rss_url)
    entries = getattr(feed, "entries", None) or []

    items: List[Dict[str, str]] = []
    scanned = 0
    for entry in entries:
        if len(items) >= limit or scanned >= max_scan:
            break
        scanned += 1
        title = str(entry.get("title", "")).strip()
        link = str(entry.get("link", "")).strip()
        if not title or not link:
            continue
        rss_description = extract_rss_description(entry)
        if category == SPORTS_CATEGORY:
            skip, reason = should_skip_article(title, link, rss_description)
            if skip:
                log.info(
                    "skip_article",
                    extra={
                        "event": "skip_article",
                        "category": category,
                        "reason": reason,
                        "title": title,
                        "link": link,
                    },
                )
                continue
        items.append(
            _entry_to_item(
                category=category,
                rss_url=rss_url,
                title=title,
                link=link,
                rss_description=rss_description,
                entry=entry,
            )
        )
    return items


def _entry_to_item(
    *,
    category: str,
    rss_url: str,
    title: str,
    link: str,
    rss_description: str,
    entry: Any,
) -> Dict[str, str]:
    return {
        "category": category,
        "title": title,
        "link": link,
        "rss_description": rss_description,
        "feed_url": rss_url,
        "pub_date_utc": extract_pub_date_utc(entry),
        "author": extract_author(entry),
    }


def fetch_latest_news_all_categories(
    *, limit: int = DEFAULT_NEWS_LIMIT, max_scan: int = DEFAULT_MAX_RSS_SCAN
) -> Dict[str, List[Dict[str, str]]]:
    """모든 카테고리의 최신 뉴스를 각각 최대 limit건씩 가져온다."""
    return {
        category: fetch_latest_news(category, limit=limit, max_scan=max_scan)
        for category in RSS_FEEDS
    }


if __name__ == "__main__":
    from main import logger, run_pipeline

    logger.info("fetcher_cli_start", extra={"event": "fetcher_cli_start"})
    summary = run_pipeline()
    logger.info(
        "pipeline_summary",
        extra={"event": "pipeline_summary", "stats": summary, "stats_json": json.dumps(summary, ensure_ascii=False)},
    )
