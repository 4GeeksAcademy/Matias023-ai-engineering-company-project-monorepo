"""HTTP security and error handling tests for RFP SSE."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import rfp_intake
from security import get_current_user


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(rfp_intake.router)
    return application


def test_sse_requires_authentication(app):
    with TestClient(app) as client:
        response = client.get("/rfp/events")

    assert response.status_code == 401


def test_sse_rejects_invalid_cursor(app):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        uuid="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
        id=101,
        email="usuario@example.invalid",
        role="user",
        is_active=True,
    )

    with TestClient(app) as client:
        response = client.get(
            "/rfp/events",
            headers={"Last-Event-ID": "invalid-cursor"},
        )

    assert response.status_code == 400


def test_sse_returns_503_when_redis_unavailable(app, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        uuid="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
        id=101,
        email="usuario@example.invalid",
        role="user",
        is_active=True,
    )

    def unavailable():
        raise RuntimeError("Simulated Redis outage")

    monkeypatch.setattr(rfp_intake, "make_client", unavailable)

    with TestClient(app) as client:
        response = client.get("/rfp/events")

    assert response.status_code == 503
