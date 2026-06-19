"""뉴스 저장소 — SQLAlchemy + `DATABASE_URL`. news-summarizer-service만 직접 접근."""

from __future__ import annotations

import os
import logging
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Set

from dotenv import load_dotenv
from sqlalchemy import DateTime, Index, String, Text, create_engine, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from json_logging import SCHEDULER_TIMEZONE

_SERVICE_DIR = Path(__file__).resolve().parent
load_dotenv(_SERVICE_DIR / ".env", encoding="utf-8-sig")
load_dotenv(encoding="utf-8-sig")

FETCH_BATCH_HOUR_KST = 11
logger = logging.getLogger("news-summarizer")


def _default_database_url() -> str:
    """레거시 `NEWS_DB_PATH` 또는 서비스 디렉터리 기준 기본 SQLite."""
    raw = os.getenv("NEWS_DB_PATH", "").strip()
    if not raw:
        return "sqlite:///./news.db"
    p = Path(raw).expanduser()
    abs_p = (p if p.is_absolute() else (_SERVICE_DIR / p)).resolve()
    return f"sqlite:///{abs_p.as_posix()}"


DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or _default_database_url()

_connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    echo=False,
    pool_pre_ping=not DATABASE_URL.startswith("sqlite"),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class SummarizedNews(Base):
    __tablename__ = "summarized_news"
    __table_args__ = (
        Index("idx_summarized_news_batch_date_kst", "batch_date_kst", "category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text(), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    # MySQL utf8mb4 + UNIQUE index length limit(3072 bytes) safe bound.
    link: Mapped[str] = mapped_column(String(700), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    batch_date_kst: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scheduled_run_time_kst: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collected_at_kst: Mapped[str | None] = mapped_column(String(64), nullable=True)
    s3_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class NewsletterRowsResult(NamedTuple):
    rows: List[Dict[str, Any]]
    batch_date_kst: str
    is_fallback: bool


def save_news(news_data: Dict[str, Any]) -> bool:
    required = ("category", "title", "summary", "link")
    for key in required:
        if key not in news_data:
            raise KeyError(f"news_data에 '{key}' 키가 필요합니다.")

    row = SummarizedNews(
        category=str(news_data["category"]),
        title=str(news_data["title"]),
        summary=str(news_data["summary"]),
        link=str(news_data["link"]),
        batch_date_kst=news_data.get("batch_date_kst"),
        scheduled_run_time_kst=news_data.get("scheduled_run_time_kst"),
        collected_at_kst=news_data.get("collected_at_kst"),
        s3_key=news_data.get("s3_key"),
    )
    with SessionLocal() as session:
        session.add(row)
        try:
            session.commit()
            return True
        except OperationalError as exc:
            session.rollback()
            logger.critical(
                "DB 저장에 실패했습니다",
                extra={
                    "event": "database_connection_failed",
                    "operation": "save_news",
                    "error": str(exc),
                    "error_type": "OperationalError",
                },
            )
            raise
        except IntegrityError:
            session.rollback()
            return False


def get_existing_links(links: List[str]) -> Set[str]:
    clean_links = [str(link).strip() for link in links if str(link).strip()]
    if not clean_links:
        return set()
    try:
        with SessionLocal() as session:
            found = session.scalars(
                select(SummarizedNews.link).where(SummarizedNews.link.in_(clean_links))
            ).all()
    except OperationalError as exc:
        logger.critical(
            "DB 조회에 실패했습니다",
            extra={
                "event": "database_connection_failed",
                "operation": "get_existing_links",
                "error": str(exc),
                "error_type": "OperationalError",
            },
        )
        raise
    return {str(link) for link in found}


def _batch_window_utc(batch_date: date) -> tuple[str, str]:
    batch_start_kst = datetime.combine(
        batch_date,
        time(hour=FETCH_BATCH_HOUR_KST, minute=0),
        tzinfo=SCHEDULER_TIMEZONE,
    )
    batch_end_kst = batch_start_kst + timedelta(days=1)
    batch_start_utc = batch_start_kst.astimezone(timezone.utc)
    batch_end_utc = batch_end_kst.astimezone(timezone.utc)
    return (
        batch_start_utc.strftime("%Y-%m-%d %H:%M:%S"),
        batch_end_utc.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _query_rows_for_batch_date(session: Any, batch_date_kst: str) -> List[Dict[str, Any]]:
    q = text(
        """
        SELECT category, title, summary, link, created_at, batch_date_kst, scheduled_run_time_kst
        FROM summarized_news
        WHERE batch_date_kst = :bd
        ORDER BY category ASC, id DESC
        """
    )
    rows = session.execute(q, {"bd": batch_date_kst}).mappings().all()
    return [_mapping_row(r) for r in rows]


def _query_rows_for_legacy_created_window(session: Any, batch_date: date) -> List[Dict[str, Any]]:
    start, end = _batch_window_utc(batch_date)
    q = text(
        """
        SELECT category, title, summary, link, created_at,
               NULL AS batch_date_kst, NULL AS scheduled_run_time_kst
        FROM summarized_news
        WHERE created_at >= :start_utc AND created_at < :end_utc
        ORDER BY category ASC, id DESC
        """
    )
    rows = session.execute(q, {"start_utc": start, "end_utc": end}).mappings().all()
    return [_mapping_row(r) for r in rows]


def _latest_batch_date_on_or_before(session: Any, batch_date: date) -> str | None:
    q = text(
        """
        SELECT MAX(batch_date_kst)
        FROM summarized_news
        WHERE batch_date_kst IS NOT NULL
          AND batch_date_kst <= :bd
        """
    )
    value = session.execute(q, {"bd": batch_date.isoformat()}).scalar()
    return str(value) if value else None


def _latest_batch_date_for_category_on_or_before(
    session: Any,
    batch_date: date,
    category: str,
) -> str | None:
    q = text(
        """
        SELECT MAX(batch_date_kst)
        FROM summarized_news
        WHERE batch_date_kst IS NOT NULL
          AND batch_date_kst <= :bd
          AND category = :category
        """
    )
    value = session.execute(
        q,
        {"bd": batch_date.isoformat(), "category": category},
    ).scalar()
    return str(value) if value else None


def resolve_newsletter_rows_for_batch(
    batch_date: date,
    *,
    fallback_to_latest: bool = False,
    category: str | None = None,
) -> NewsletterRowsResult:
    """Resolve newsletter rows and report whether a prior batch was used."""
    requested = batch_date.isoformat()
    try:
        with SessionLocal() as session:
            rows = _query_rows_for_batch_date(session, requested)
            if category is not None:
                rows = [row for row in rows if str(row.get("category", "")) == category]
            if rows:
                return NewsletterRowsResult(rows=rows, batch_date_kst=requested, is_fallback=False)

            if fallback_to_latest:
                latest = (
                    _latest_batch_date_for_category_on_or_before(session, batch_date, category)
                    if category is not None
                    else _latest_batch_date_on_or_before(session, batch_date)
                )
                if latest and latest != requested:
                    fallback_rows = _query_rows_for_batch_date(session, latest)
                    if category is not None:
                        fallback_rows = [
                            row for row in fallback_rows if str(row.get("category", "")) == category
                        ]
                    if fallback_rows:
                        return NewsletterRowsResult(rows=fallback_rows, batch_date_kst=latest, is_fallback=True)

            legacy_rows = _query_rows_for_legacy_created_window(session, batch_date)
            if category is not None:
                legacy_rows = [
                    row for row in legacy_rows if str(row.get("category", "")) == category
                ]
            return NewsletterRowsResult(rows=legacy_rows, batch_date_kst=requested, is_fallback=False)
    except OperationalError as exc:
        logger.critical(
            "DB 조회에 실패했습니다",
            extra={
                "event": "database_connection_failed",
                "operation": "list_newsletter_rows_for_batch",
                "error": str(exc),
                "error_type": "OperationalError",
            },
        )
        raise


def list_newsletter_rows_for_batch(
    batch_date: date,
    *,
    fallback_to_latest: bool = False,
) -> List[Dict[str, Any]]:
    """메일 뉴스레터용: batch_date_kst 우선, 없으면 created_at UTC 구간 폴백."""
    return resolve_newsletter_rows_for_batch(
        batch_date,
        fallback_to_latest=fallback_to_latest,
    ).rows


def _mapping_row(r: Any) -> Dict[str, Any]:
    d = dict(r)
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    return d
