"""CI smoke tests for news-summarizer-service.

Ports: User 8000, Mail 8002, Summarizer 8004.
뉴스 DB는 본 서비스의 SQLAlchemy만 사용 — 타 서비스 database 모듈을 import하지 않습니다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app  # noqa: E402 — conftest.py applied migrations first


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_health_returns_200_json_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
