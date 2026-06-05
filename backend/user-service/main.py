from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from json_logging import (
    SCHEDULER_TIMEZONE,
    register_scheduler_logging,
    reset_trace_id,
    resolve_request_trace_id,
    set_trace_id,
    setup_service_logging,
    uvicorn_log_config,
)
from models import Subscription
from category_slugs import resolve_category_slug
from schemas import InternalSubscriberOut, SubscribeCreate, SubscribeResponse
from unsubscribe_pages import (
    already_unsubscribed_html,
    confirm_unsubscribe_html,
    invalid_link_html,
    unsubscribe_complete_html,
)

MAIL_SERVICE_URL = os.environ.get("MAIL_SERVICE_URL", "http://localhost:8002").rstrip("/")
NEWS_API_BASE_URL = os.environ.get("NEWS_API_BASE_URL", "http://localhost:8004").rstrip("/")
INTERNAL_API_TOKEN = os.environ.get("INTERNAL_API_TOKEN", "").strip()
NEWS_API_HTTP_TIMEOUT = 10.0
DEFAULT_SCHEDULER_HEARTBEAT_MINUTES = 60

_CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ALLOW_ORIGINS",
        "https://patrasche.cloud,http://localhost:5173",
    ).split(",")
    if origin.strip()
]

logger = setup_service_logging("user-service")
scheduler = AsyncIOScheduler(timezone=SCHEDULER_TIMEZONE)
register_scheduler_logging(scheduler, logger, service_name="user-service")


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _subscription_snapshot_job() -> dict[str, int]:
    with SessionLocal() as db:
        total = int(db.query(func.count(Subscription.id)).scalar() or 0)
        verified = int(
            db.query(func.count(Subscription.id))
            .filter(Subscription.is_verified.is_(True))
            .scalar()
            or 0
        )
    return {
        "subscription_total": total,
        "verified_total": verified,
        "pending_verification_total": max(total - verified, 0),
    }


def _configure_scheduler_jobs() -> int:
    interval_minutes = max(
        1,
        _env_int("SCHEDULER_HEARTBEAT_MINUTES", DEFAULT_SCHEDULER_HEARTBEAT_MINUTES),
    )
    scheduler.add_job(
        _subscription_snapshot_job,
        trigger="interval",
        minutes=interval_minutes,
        id="user-service-subscription-snapshot",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=max(60, interval_minutes * 60),
        next_run_time=datetime.now(SCHEDULER_TIMEZONE),
    )
    return interval_minutes


@asynccontextmanager
async def lifespan(_app: FastAPI):
    interval_minutes = _configure_scheduler_jobs()
    if not scheduler.running:
        scheduler.start()
    logger.info(
        "유저 서비스가 시작되었습니다",
        extra={
            "event": "service_startup",
            "scheduler_timezone": str(SCHEDULER_TIMEZONE),
            "scheduler_heartbeat_minutes": interval_minutes,
        },
    )
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


app = FastAPI(title="User Service", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    trace_id = resolve_request_trace_id(request.headers.get("x-trace-id"))
    token = set_trace_id(trace_id)
    try:
        response = await call_next(request)
        response.headers["x-trace-id"] = trace_id
        return response
    finally:
        reset_trace_id(token)


def _serialize_categories(categories: list[str]) -> str:
    cleaned = [c.strip() for c in categories if c and c.strip()]
    return ",".join(cleaned)


def _deserialize_categories(category_csv: str) -> list[str]:
    if not category_csv:
        return []
    return [c.strip() for c in category_csv.split(",") if c.strip()]


@app.get("/health")
def health_check():
    logger.info(
        "헬스체크 정상",
        extra={"event": "health_check_requested"},
    )
    return {"status": "ok"}


@app.get("/api/news/list")
async def api_news_list(
    category: str = Query(..., min_length=1),
    batch_date: date | None = None,
):
    if resolve_category_slug(category) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"허용되지 않은 category slug입니다: {category}",
        )

    params: dict[str, str] = {"category": category}
    if batch_date is not None:
        params["batch_date"] = batch_date.isoformat()

    url = f"{NEWS_API_BASE_URL}/internal/news/list"
    try:
        async with httpx.AsyncClient(timeout=NEWS_API_HTTP_TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        logger.error(
            "뉴스 목록 조회 타임아웃",
            extra={"event": "news_list_upstream_timeout", "category": category},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="뉴스 서비스 응답 시간 초과",
        ) from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else 502
        logger.error(
            "뉴스 목록 조회 HTTP 오류",
            extra={
                "event": "news_list_upstream_http_error",
                "category": category,
                "upstream_status": status_code,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="뉴스 서비스 오류",
        ) from exc
    except httpx.RequestError as exc:
        logger.error(
            "뉴스 목록 조회 네트워크 오류",
            extra={"event": "news_list_upstream_network_error", "category": category},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="뉴스 서비스에 연결할 수 없습니다",
        ) from exc

    if isinstance(payload, list):
        return {"items": payload}
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return {"items": payload["items"]}
    return {"items": []}


def _require_internal_access(request: Request) -> None:
    if not INTERNAL_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="internal API is not configured",
        )
    token = request.headers.get("x-internal-token", "").strip()
    if token != INTERNAL_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="internal API access denied",
        )


def _find_by_unsubscribe_token(db: Session, token: str) -> Subscription | None:
    raw = (token or "").strip()
    if not raw:
        return None
    return (
        db.query(Subscription)
        .filter(Subscription.unsubscribe_token == raw)
        .first()
    )


@app.get("/internal/subscribers", response_model=list[InternalSubscriberOut])
def internal_subscribers(
    request: Request,
    db: Session = Depends(get_db),
):
    """인증 완료 구독자 목록 (mail-service 뉴스레터 등 내부 연동용)."""
    _require_internal_access(request)
    try:
        rows = (
            db.query(Subscription)
            .filter(
                Subscription.is_verified.is_(True),
                Subscription.is_active.is_(True),
            )
            .order_by(Subscription.id.asc())
            .all()
        )
    except OperationalError as exc:
        logger.critical(
            "DB 조회에 실패했습니다",
            extra={
                "event": "database_connection_failed",
                "operation": "internal_subscribers",
                "error": str(exc),
                "error_type": "OperationalError",
            },
        )
        raise
    return [
        InternalSubscriberOut(
            email=r.email,
            interest_categories=_deserialize_categories(r.category or ""),
            unsubscribe_token=r.unsubscribe_token,
        )
        for r in rows
    ]


def _format_categories_for_popup(categories: list[str]) -> str:
    return ", ".join(categories)


async def send_verification_email(email: str, token: str) -> None:
    logger.info(
        "인증 메일 발송을 시작합니다",
        extra={"event": "verification_email_send_attempt", "user_email": email},
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{MAIL_SERVICE_URL}/send-verify-email",
                json={"email": email, "token": token},
            )
            response.raise_for_status()
            status_code = response.status_code
    except httpx.HTTPStatusError as exc:
        sc = exc.response.status_code if exc.response is not None else None
        logger.error(
            "인증 메일 발송 HTTP 오류",
            extra={
                "event": "verification_email_send_failure",
                "user_email": email,
                "http_status": sc,
                "reason": str(exc),
            },
        )
        raise
    except httpx.RequestError as exc:
        logger.error(
            "인증 메일 발송 네트워크 오류",
            extra={
                "event": "verification_email_send_failure",
                "user_email": email,
                "reason": str(exc),
            },
        )
        raise

    logger.info(
        "인증 메일 발송 성공",
        extra={
            "event": "verification_email_send_success",
            "user_email": email,
            "http_status": status_code,
        },
    )


@app.post(
    "/subscribe",
    response_model=SubscribeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def subscribe(
    payload: SubscribeCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    logger.info(
        "구독 요청을 받았습니다",
        extra={"event": "subscribe_request_received", "user_email": payload.email},
    )
    try:
        existing = db.query(Subscription).filter(Subscription.email == payload.email).first()
    except OperationalError as exc:
        logger.critical(
            "DB 조회에 실패했습니다",
            extra={
                "event": "database_connection_failed",
                "operation": "subscribe_lookup",
                "error": str(exc),
                "error_type": "OperationalError",
            },
        )
        raise
    category_csv = _serialize_categories(payload.category)
    if not category_csv:
        logger.warning(
            "구독 카테고리가 비어 있습니다",
            extra={"event": "subscribe_empty_category", "user_email": payload.email},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="category는 최소 1개 이상의 값이 필요합니다.",
        )

    if existing:
        if existing.is_active:
            logger.warning(
                "이미 구독된 이메일입니다",
                extra={"event": "subscribe_duplicate_email", "user_email": payload.email},
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "이미 구독된 이메일입니다.",
                    "verification_pending": not existing.is_verified,
                },
            )
        existing.is_active = True
        existing.category = category_csv
        existing.unsubscribe_token = secrets.token_urlsafe(32)
        send_verification = False
        if existing.is_verified:
            logger.info(
                "취소된 구독을 재활성했습니다",
                extra={
                    "event": "subscription_reactivated_verified",
                    "user_email": payload.email,
                },
            )
        else:
            existing.verification_token = secrets.token_urlsafe(32)
            send_verification = True
            logger.info(
                "미인증 취소 구독을 재활성했습니다",
                extra={
                    "event": "subscription_reactivated_unverified",
                    "user_email": payload.email,
                },
            )
        try:
            db.commit()
            db.refresh(existing)
        except OperationalError as exc:
            db.rollback()
            logger.critical(
                "DB 저장에 실패했습니다",
                extra={
                    "event": "database_connection_failed",
                    "operation": "subscribe_reactivate_commit",
                    "error": str(exc),
                    "error_type": "OperationalError",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="DB 연결에 실패했습니다.",
            ) from exc
        if send_verification:
            background_tasks.add_task(
                send_verification_email,
                payload.email,
                existing.verification_token,
            )
            return SubscribeResponse(
                message="구독 신청 완료, 인증 메일 발송 대기",
                email=existing.email,
                category=_format_categories_for_popup(_deserialize_categories(existing.category)),
                verification_pending=True,
            )
        return SubscribeResponse(
            message="구독이 다시 활성화되었습니다",
            email=existing.email,
            category=_format_categories_for_popup(_deserialize_categories(existing.category)),
            verification_pending=False,
        )

    verification_token = secrets.token_urlsafe(32)
    unsubscribe_token = secrets.token_urlsafe(32)
    logger.info(
        "인증·취소 토큰이 생성되었습니다",
        extra={
            "event": "subscription_tokens_generated",
            "user_email": payload.email,
        },
    )

    row = Subscription(
        email=payload.email,
        category=category_csv,
        is_verified=False,
        is_active=True,
        verification_token=verification_token,
        unsubscribe_token=unsubscribe_token,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
    except OperationalError as exc:
        db.rollback()
        logger.critical(
            "DB 저장에 실패했습니다",
            extra={
                "event": "database_connection_failed",
                "operation": "subscribe_commit",
                "error": str(exc),
                "error_type": "OperationalError",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DB 연결에 실패했습니다.",
        ) from exc
    except Exception:
        db.rollback()
        logger.exception(
            "구독 정보 저장에 실패했습니다",
            extra={"event": "subscription_persist_failed", "user_email": payload.email},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="구독 저장에 실패했습니다.",
        ) from None

    background_tasks.add_task(send_verification_email, payload.email, verification_token)
    logger.info(
        "구독이 완료되었고 인증 메일이 대기열에 등록되었습니다",
        extra={
            "event": "subscription_created_verification_queued",
            "user_email": payload.email,
            "category_count": len(_deserialize_categories(category_csv)),
        },
    )

    return SubscribeResponse(
        message="구독 신청 완료, 인증 메일 발송 대기",
        email=row.email,
        category=_format_categories_for_popup(_deserialize_categories(row.category)),
        verification_pending=True,
    )


@app.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_confirm(token: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    """Show confirm page only; never changes subscription state (scanner-safe GET)."""
    subscriber = _find_by_unsubscribe_token(db, token)
    if subscriber is None:
        logger.warning(
            "취소 링크가 유효하지 않습니다",
            extra={"event": "unsubscribe_invalid_token"},
        )
        return HTMLResponse(content=invalid_link_html(), status_code=status.HTTP_400_BAD_REQUEST)
    if not subscriber.is_active:
        return HTMLResponse(content=already_unsubscribed_html(), status_code=status.HTTP_200_OK)
    return HTMLResponse(content=confirm_unsubscribe_html(token), status_code=status.HTTP_200_OK)


@app.post("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_execute(token: str = Form(...), db: Session = Depends(get_db)):
    """Deactivate subscription; keeps unsubscribe_token for idempotent 'already cancelled'."""
    subscriber = _find_by_unsubscribe_token(db, token)
    if subscriber is None:
        logger.warning(
            "취소 요청 토큰이 유효하지 않습니다",
            extra={"event": "unsubscribe_post_invalid_token"},
        )
        return HTMLResponse(content=invalid_link_html(), status_code=status.HTTP_400_BAD_REQUEST)
    if not subscriber.is_active:
        return HTMLResponse(content=already_unsubscribed_html(), status_code=status.HTTP_200_OK)

    subscriber.is_active = False
    try:
        db.commit()
    except OperationalError as exc:
        db.rollback()
        logger.critical(
            "DB 저장에 실패했습니다",
            extra={
                "event": "database_connection_failed",
                "operation": "unsubscribe_commit",
                "error": str(exc),
                "error_type": "OperationalError",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DB 연결에 실패했습니다.",
        ) from exc
    logger.info(
        "구독이 취소되었습니다",
        extra={"event": "unsubscribe_success", "user_email": subscriber.email},
    )
    return HTMLResponse(content=unsubscribe_complete_html(), status_code=status.HTTP_200_OK)


@app.get("/verify")
def verify_subscription(email: str, token: str, db: Session = Depends(get_db)):
    logger.info(
        "이메일 인증 요청을 받았습니다",
        extra={"event": "verify_request_received", "user_email": email},
    )
    try:
        subscriber = db.query(Subscription).filter(Subscription.email == email).first()
    except OperationalError as exc:
        logger.critical(
            "DB 조회에 실패했습니다",
            extra={
                "event": "database_connection_failed",
                "operation": "verify_lookup",
                "error": str(exc),
                "error_type": "OperationalError",
            },
        )
        raise
    if not subscriber:
        logger.warning(
            "구독자를 찾을 수 없습니다",
            extra={"event": "verify_subscriber_not_found", "user_email": email},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="구독자를 찾을 수 없습니다.",
        )

    if subscriber.verification_token != token:
        logger.warning(
            "유효하지 않은 인증 토큰입니다",
            extra={"event": "verify_invalid_token", "user_email": email},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="유효하지 않은 인증 토큰입니다.",
        )

    if not subscriber.is_verified:
        subscriber.is_verified = True
        try:
            db.commit()
        except OperationalError as exc:
            db.rollback()
            logger.critical(
                "DB 저장에 실패했습니다",
                extra={
                    "event": "database_connection_failed",
                    "operation": "verify_commit",
                    "error": str(exc),
                    "error_type": "OperationalError",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="DB 연결에 실패했습니다.",
            ) from exc
        logger.info(
            "이메일 인증이 완료되었습니다",
            extra={"event": "verify_success", "user_email": email},
        )
    else:
        logger.info(
            "이미 인증된 구독자입니다",
            extra={"event": "verify_already_verified", "user_email": email},
        )

    return {"message": "인증이 완료되었습니다"}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0").strip() or "0.0.0.0"
    raw_port = os.getenv("PORT", "8000")
    try:
        port = int(raw_port) if str(raw_port).strip() else 8000
    except ValueError:
        port = 8000

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,
        log_config=uvicorn_log_config(),
    )
