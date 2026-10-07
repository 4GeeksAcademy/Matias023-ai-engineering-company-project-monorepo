"""Tests for the telemetry event storage endpoint.

The endpoint now validates per-event, stores valid events in the
telemetry_events table, and returns ``{"received", "stored", "rejected"}``.
An invalid event does NOT cancel the batch — only that event is rejected.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from main import app
from database import get_db, get_engine, reset_engine_for_tests


# ──────────────────────────────────────────────
# SQLModel test engine (isolated per module)
# ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def telemetry_engine():
    """Create a fresh in-memory SQLite engine for telemetry tests.

    Uses StaticPool so the app's worker thread and the test thread share the
    same in-memory connection.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import telemetry_models so the TelemetryEvent table gets registered
    import telemetry_models  # noqa: F401
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _safe_env(monkeypatch):
    """Remove DATABASE_URL and set safe local-dev env vars.

    Our tests use an isolated in-memory SQLite engine that we control via
    dependency overrides.  The real ``DATABASE_URL`` (which may point at an
    expired/unreachable Supabase instance) must not interfere.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "development")


@pytest.fixture
def client(telemetry_engine, _safe_env):
    """TestClient with get_db overridden to the isolated test engine."""

    def override_get_db():
        with Session(telemetry_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _make_event(**overrides):
    """Build a minimal valid telemetry event."""
    payload = {
        "eventId": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sessionId": str(uuid4()),
        "userId": str(uuid4()),
        "event_type": "page_viewed",
        "schemaVersion": "1.0",
        "requestId": str(uuid4()),
        "properties": {"page": "suppliers", "navigationType": "client_navigation"},
    }
    payload.update(overrides)
    return payload


def _batch(events):
    return {"events": events}


# ══════════════════════════════════════════════
# Basic acceptance
# ══════════════════════════════════════════════


class TestTelemetryAcceptance:
    """The endpoint exists, speaks JSON, and returns shape-correct responses."""

    def test_endpoint_exists_and_returns_json(self, client):
        response = client.post("/telemetry/events", json=_batch([_make_event()]))
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    def test_returns_stored_count(self, client):
        response = client.post(
            "/telemetry/events",
            json=_batch([_make_event(), _make_event()]),
        )
        data = response.json()
        assert data["received"] == 2
        assert data["stored"] == 2
        assert data["rejected"] == 0

    def test_accepts_single_event(self, client):
        response = client.post(
            "/telemetry/events",
            json=_batch([_make_event()]),
        )
        assert response.status_code == 200
        assert response.json()["stored"] == 1

    def test_accepts_multiple_events(self, client):
        events = [_make_event() for _ in range(5)]
        response = client.post("/telemetry/events", json=_batch(events))
        assert response.status_code == 200
        assert response.json()["stored"] == 5


# ══════════════════════════════════════════════
# Edge cases
# ══════════════════════════════════════════════


class TestTelemetryEdgeCases:
    """Boundary conditions and malformed inputs."""

    def test_empty_batch_returns_zero(self, client):
        response = client.post("/telemetry/events", json=_batch([]))
        assert response.status_code == 200
        assert response.json() == {"received": 0, "stored": 0, "rejected": 0}

    def test_missing_event_type_rejected(self, client):
        """An event missing event_type is individually rejected.

        Since this is the only event in the batch, received=1, stored=0,
        rejected=1 (HTTP 200, not 422).
        """
        bad = _make_event()
        del bad["event_type"]
        response = client.post("/telemetry/events", json=_batch([bad]))
        assert response.status_code == 200
        assert response.json() == {"received": 1, "stored": 0, "rejected": 1}

    def test_invalid_uuid_rejected(self, client):
        """Invalid UUID is rejected per-event — HTTP 200 with rejected=1."""
        bad = _make_event(eventId="not-a-uuid")
        response = client.post("/telemetry/events", json=_batch([bad]))
        assert response.status_code == 200
        assert response.json() == {"received": 1, "stored": 0, "rejected": 1}

    def test_missing_timestamp_rejected(self, client):
        bad = _make_event()
        del bad["timestamp"]
        response = client.post("/telemetry/events", json=_batch([bad]))
        assert response.status_code == 200
        assert response.json()["rejected"] == 1

    def test_non_list_events_rejected(self, client):
        """If 'events' is not a list (e.g. a string), we treat it as empty."""
        response = client.post(
            "/telemetry/events",
            json={"events": "not_an_array"},
        )
        assert response.status_code == 200
        assert response.json() == {"received": 0, "stored": 0, "rejected": 0}

    def test_missing_events_key_rejected(self, client):
        """No 'events' key -> received=0."""
        response = client.post("/telemetry/events", json={})
        assert response.status_code == 200
        assert response.json() == {"received": 0, "stored": 0, "rejected": 0}

    def test_batch_with_mixed_valid_invalid_events(self, client):
        """Invalid events DO NOT cancel the batch — only the bad ones are rejected."""
        valid = _make_event()
        invalid = _make_event(eventId="bad-uuid")
        response = client.post(
            "/telemetry/events",
            json=_batch([valid, invalid]),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["received"] == 2
        assert data["stored"] == 1
        assert data["rejected"] == 1

    def test_large_properties_accepted(self, client):
        """Properties is a free-form dict — any JSON object is valid."""
        event = _make_event(
            properties={
                "page": "incidents_list",
                "filters": {"status": "open", "priority": "high"},
            },
        )
        response = client.post("/telemetry/events", json=_batch([event]))
        assert response.status_code == 200
        assert response.json()["stored"] == 1


# ══════════════════════════════════════════════
# Persistence / idempotency
# ══════════════════════════════════════════════


class TestTelemetryPersistence:
    """Events are persisted in telemetry_events."""

    def test_repeat_same_event_idempotent(self, client):
        """Same eventId repeated -> first write wins, second is silently skipped.

        The endpoint stores the event on the first call (stored=1).
        The second call with the same eventId fails the PK constraint,
        so stored=0 but the call still succeeds (idempotent).
        """
        event = _make_event()
        r1 = client.post("/telemetry/events", json=_batch([event]))
        assert r1.json()["stored"] == 1

        r2 = client.post("/telemetry/events", json=_batch([event]))
        assert r2.status_code == 200
        assert r2.json()["stored"] == 0

    def test_get_not_allowed(self, client):
        """The endpoint is write-only."""
        response = client.get("/telemetry/events")
        assert response.status_code == 405