"""Tests for unsubscribe flow (GET confirm, POST cancel, internal filter)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from database import SessionLocal
from main import app
from models import Subscription

_INTERNAL_HEADERS = {"x-internal-token": "test-internal-token"}


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _create_subscription(
    *,
    email: str,
    is_verified: bool = False,
    is_active: bool = True,
) -> Subscription:
    import secrets

    with SessionLocal() as db:
        row = Subscription(
            email=email,
            category="IT/테크",
            is_verified=is_verified,
            is_active=is_active,
            verification_token=secrets.token_urlsafe(32),
            unsubscribe_token=secrets.token_urlsafe(32),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


def test_subscribe_active_verified_returns_409_without_verification_pending(
    client: TestClient,
) -> None:
    email = f"dup-verified-{uuid.uuid4().hex}@example.com"
    _create_subscription(email=email, is_verified=True, is_active=True)

    response = client.post(
        "/subscribe",
        json={"email": email, "category": ["tech"]},
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["verification_pending"] is False
    assert "이미 구독" in detail["message"]


def test_subscribe_active_unverified_returns_409_with_verification_pending(
    client: TestClient,
) -> None:
    email = f"dup-unverified-{uuid.uuid4().hex}@example.com"
    _create_subscription(email=email, is_verified=False, is_active=True)

    response = client.post(
        "/subscribe",
        json={"email": email, "category": ["tech"]},
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["verification_pending"] is True
    assert "이미 구독" in detail["message"]


@patch("main.send_verification_email", new_callable=AsyncMock)
def test_subscribe_sets_unsubscribe_token(_mock_mail: AsyncMock, client: TestClient) -> None:
    email = f"new-{uuid.uuid4().hex}@example.com"
    response = client.post(
        "/subscribe",
        json={"email": email, "category": ["tech"]},
    )
    assert response.status_code == 201
    with SessionLocal() as db:
        row = db.query(Subscription).filter(Subscription.email == email).first()
        assert row is not None
        assert row.unsubscribe_token
        assert row.is_active is True


def test_get_unsubscribe_does_not_deactivate(client: TestClient) -> None:
    row = _create_subscription(email=f"get-{uuid.uuid4().hex}@example.com")
    response = client.get("/unsubscribe", params={"token": row.unsubscribe_token})
    assert response.status_code == 200
    assert "구독을 취소하시겠습니까" in response.text
    with SessionLocal() as db:
        refreshed = db.get(Subscription, row.id)
        assert refreshed is not None
        assert refreshed.is_active is True


def test_post_unsubscribe_deactivates_and_keeps_token(client: TestClient) -> None:
    row = _create_subscription(email=f"post-{uuid.uuid4().hex}@example.com", is_verified=True)
    token = row.unsubscribe_token
    response = client.post("/unsubscribe", data={"token": token})
    assert response.status_code == 200
    assert "구독이 취소되었습니다" in response.text
    with SessionLocal() as db:
        refreshed = db.get(Subscription, row.id)
        assert refreshed is not None
        assert refreshed.is_active is False
        assert refreshed.unsubscribe_token == token


def test_post_unsubscribe_invalid_token_returns_400_html(client: TestClient) -> None:
    response = client.post("/unsubscribe", data={"token": "not-a-real-token"})
    assert response.status_code == 400
    assert "유효하지 않은 링크" in response.text


def test_post_unsubscribe_already_cancelled(client: TestClient) -> None:
    row = _create_subscription(
        email=f"cancelled-{uuid.uuid4().hex}@example.com",
        is_verified=True,
        is_active=False,
    )
    response = client.post("/unsubscribe", data={"token": row.unsubscribe_token})
    assert response.status_code == 200
    assert "이미 취소된 구독" in response.text


def test_internal_subscribers_excludes_inactive_unverified(client: TestClient) -> None:
    active_email = f"active-{uuid.uuid4().hex}@example.com"
    inactive_email = f"inactive-{uuid.uuid4().hex}@example.com"
    _create_subscription(email=active_email, is_verified=True, is_active=True)
    _create_subscription(email=inactive_email, is_verified=True, is_active=False)

    response = client.get("/internal/subscribers", headers=_INTERNAL_HEADERS)
    assert response.status_code == 200
    emails = {item["email"] for item in response.json()}
    assert active_email in emails
    assert inactive_email not in emails


def test_internal_subscribers_requires_token(client: TestClient) -> None:
    response = client.get("/internal/subscribers")
    assert response.status_code == 403


def test_internal_subscribers_503_when_token_not_configured(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("main.INTERNAL_API_TOKEN", "")
    response = client.get("/internal/subscribers", headers=_INTERNAL_HEADERS)
    assert response.status_code == 503


def test_internal_subscribers_excludes_active_unverified(client: TestClient) -> None:
    verified_email = f"verified-{uuid.uuid4().hex}@example.com"
    unverified_email = f"unverified-{uuid.uuid4().hex}@example.com"
    _create_subscription(email=verified_email, is_verified=True, is_active=True)
    _create_subscription(email=unverified_email, is_verified=False, is_active=True)

    response = client.get("/internal/subscribers", headers=_INTERNAL_HEADERS)
    assert response.status_code == 200
    emails = {item["email"] for item in response.json()}
    assert verified_email in emails
    assert unverified_email not in emails


@patch("main.send_verification_email", new_callable=AsyncMock)
def test_resubscribe_reactivates_and_regenerates_unsubscribe_token(
    _mock_mail: AsyncMock,
    client: TestClient,
) -> None:
    email = f"resub-{uuid.uuid4().hex}@example.com"
    row = _create_subscription(email=email, is_verified=True, is_active=False)
    old_unsub = row.unsubscribe_token

    response = client.post(
        "/subscribe",
        json={"email": email, "category": ["economy"]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["verification_pending"] is False
    assert "다시 활성화" in body["message"]
    _mock_mail.assert_not_called()

    with SessionLocal() as db:
        refreshed = db.query(Subscription).filter(Subscription.email == email).first()
        assert refreshed is not None
        assert refreshed.is_active is True
        assert refreshed.category == "경제"
        assert refreshed.unsubscribe_token != old_unsub
        assert refreshed.is_verified is True

    stale_get = client.get("/unsubscribe", params={"token": old_unsub})
    assert stale_get.status_code == 400


@patch("main.send_verification_email", new_callable=AsyncMock)
def test_resubscribe_unverified_sends_verification_mail(
    mock_mail: AsyncMock,
    client: TestClient,
) -> None:
    email = f"unverified-resub-{uuid.uuid4().hex}@example.com"
    _create_subscription(email=email, is_verified=False, is_active=False)

    response = client.post(
        "/subscribe",
        json={"email": email, "category": ["tech"]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["verification_pending"] is True
    mock_mail.assert_called_once()
