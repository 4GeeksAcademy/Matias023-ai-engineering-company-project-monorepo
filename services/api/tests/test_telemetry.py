"""Tests for the telemetry event storage endpoint (corrected schema).

Tests the 8-column schema and mapping defined by the exercise specification.

Schema:
  id, timestamp, service, event_type, level, value, message, tags

The endpoint validates per-event, stores valid events in the
telemetry_events table, and returns ``{"received", "stored", "rejected"}``.
An invalid event does NOT cancel the batch — only that event is rejected.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool

from sqlalchemy import text as sa_text

from main import app
from database import get_db, get_engine, reset_engine_for_tests
from telemetry_models import TelemetryEventTable


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
    # Import telemetry_models so the TelemetryEventTable table gets registered
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


@pytest.fixture(autouse=True)
def _clean_telemetry_events(telemetry_engine):
    """Delete all telemetry_events rows before each test to prevent accumulation.

    The engine is module-scoped (shared across tests), so without cleanup
    each test inherits rows inserted by previous tests.
    """
    with Session(telemetry_engine) as session:
        session.exec(sa_text("DELETE FROM telemetry_events"))
        session.commit()
    yield


@pytest.fixture
def client(telemetry_engine, _safe_env, _clean_telemetry_events):
    """TestClient with get_db overridden to the isolated test engine."""

    def override_get_db():
        with Session(telemetry_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)


# ──────────────────────────────────────────────
# Query helper
# ──────────────────────────────────────────────


def _query_all(telemetry_engine) -> list[TelemetryEventTable]:
    """Return all rows from telemetry_events via the test engine."""
    with Session(telemetry_engine) as session:
        return list(session.exec(select(TelemetryEventTable)).all())


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
        response = client.post("/telemetry/events",
                               json=_batch([_make_event()]))
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

    def test_missing_schema_version_rejected(self, client):
        """An event without schemaVersion is rejected individually."""
        bad = _make_event()
        del bad["schemaVersion"]
        response = client.post("/telemetry/events", json=_batch([bad]))
        assert response.status_code == 200
        assert response.json() == {"received": 1, "stored": 0, "rejected": 1}

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
# Schema verification — the 8 required columns
# ══════════════════════════════════════════════


class TestTelemetrySchema:
    """Verify that stored rows match the required 8-column schema."""

    def test_event_stored_with_correct_schema(self, client, telemetry_engine):
        """A valid event creates a row with all 8 columns populated correctly."""
        event = _make_event(
            event_type="incident_created",
            properties={
                "incident_id": 42,
                "category": "lost_parcel",
                "origin": "branch",
                "branch": "la_warehouse",
                "status": "open",
            },
        )
        response = client.post("/telemetry/events", json=_batch([event]))
        assert response.status_code == 200
        assert response.json()["stored"] == 1

        rows = _query_all(telemetry_engine)
        assert len(rows) == 1
        row = rows[0]

        # All 8 columns are present
        assert row.id is not None
        assert row.timestamp is not None
        assert row.service is not None
        assert row.event_type is not None
        assert row.level is not None
        # value is nullable
        # message is nullable
        assert row.tags is not None

    def test_service_correct_for_backend_event(self, client, telemetry_engine):
        """Backend events get service='api'."""
        event = _make_event(event_type="incident_created")
        client.post("/telemetry/events", json=_batch([event]))
        rows = _query_all(telemetry_engine)
        assert rows[0].service == "api"

    def test_service_correct_for_frontend_event(self, client, telemetry_engine):
        """Frontend events get service='backoffice'."""
        event = _make_event(event_type="page_viewed")
        client.post("/telemetry/events", json=_batch([event]))
        rows = _query_all(telemetry_engine)
        assert rows[0].service == "backoffice"

    def test_event_type_persisted(self, client, telemetry_engine):
        """event_type is stored correctly."""
        event = _make_event(event_type="sku_created")
        client.post("/telemetry/events", json=_batch([event]))
        rows = _query_all(telemetry_engine)
        assert rows[0].event_type == "sku_created"

    def test_level_default_is_info(self, client, telemetry_engine):
        """Default level is 'info'."""
        event = _make_event(event_type="page_viewed")
        client.post("/telemetry/events", json=_batch([event]))
        rows = _query_all(telemetry_engine)
        assert rows[0].level == "info"

    def test_level_error_for_error_events(self, client, telemetry_engine):
        """Error events get level='error'."""
        event = _make_event(event_type="api_server_error")
        client.post("/telemetry/events", json=_batch([event]))
        rows = _query_all(telemetry_engine)
        assert rows[0].level == "error"

    def test_level_warning_for_warning_events(self, client, telemetry_engine):
        """Warning events get level='warn'."""
        event = _make_event(event_type="outbound_insufficient_stock")
        client.post("/telemetry/events", json=_batch([event]))
        rows = _query_all(telemetry_engine)
        assert rows[0].level == "warn"

    def test_value_nullable(self, client, telemetry_engine):
        """Events without a numeric value have value=NULL."""
        event = _make_event(event_type="page_viewed")
        client.post("/telemetry/events", json=_batch([event]))
        rows = _query_all(telemetry_engine)
        assert rows[0].value is None

    def test_value_numeric(self, client, telemetry_engine):
        """Events with a numeric property extract the value."""
        event = _make_event(
            event_type="inventory_query_duration",
            properties={"endpoint": "/inventory/products", "duration_ms": 45},
        )
        client.post("/telemetry/events", json=_batch([event]))
        rows = _query_all(telemetry_engine)
        assert rows[0].value == 45.0

    def test_message_nullable(self, client, telemetry_engine):
        """Events without a known mapping have message=NULL."""
        event = _make_event(
            event_type="some_unknown_event_type", properties={})
        client.post("/telemetry/events", json=_batch([event]))
        rows = _query_all(telemetry_engine)
        assert rows[0].message is None

    def test_message_generated(self, client, telemetry_engine):
        """Events with known types get a human-readable message."""
        event = _make_event(
            event_type="incident_created",
            properties={
                "incident_id": 42,
                "category": "lost_parcel",
                "origin": "branch",
                "branch": "la_warehouse",
                "status": "open",
            },
        )
        client.post("/telemetry/events", json=_batch([event]))
        rows = _query_all(telemetry_engine)
        assert rows[0].message is not None
        assert "lost_parcel" in rows[0].message

    def test_tags_preserved(self, client, telemetry_engine):
        """Original event properties are preserved in tags."""
        props = {"page": "suppliers", "navigationType": "client_navigation"}
        event = _make_event(event_type="page_viewed", properties=props)
        client.post("/telemetry/events", json=_batch([event]))
        rows = _query_all(telemetry_engine)
        assert rows[0].tags is not None
        assert rows[0].tags.get("page") == "suppliers"
        assert rows[0].tags.get("navigationType") == "client_navigation"

    def test_tags_preserves_envelope_dimensions(self, client, telemetry_engine):
        """Envelope dimensions (eventId, sessionId, userId, etc.) are stored in tags."""
        event = _make_event(
            event_type="page_viewed",
            properties={"page": "login"},
        )
        client.post("/telemetry/events", json=_batch([event]))
        rows = _query_all(telemetry_engine)
        tags = rows[0].tags
        assert "eventId" in tags
        assert "sessionId" in tags
        assert "userId" in tags
        assert "schemaVersion" in tags
        assert "requestId" in tags

    def test_timestamp_persisted(self, client, telemetry_engine):
        """The event timestamp is stored correctly."""
        event = _make_event()
        client.post("/telemetry/events", json=_batch([event]))
        rows = _query_all(telemetry_engine)
        # The stored timestamp should be a datetime object
        assert rows[0].timestamp is not None
        assert isinstance(rows[0].timestamp, datetime)


# ══════════════════════════════════════════════
# Persistence / idempotency
# ══════════════════════════════════════════════


class TestTelemetryPersistence:
    """Events are persisted in telemetry_events."""

    def test_repeat_same_event_idempotent(self, client, telemetry_engine):
        """Same eventId repeated -> first write wins, second is silently skipped.

        The endpoint stores the event on the first call (stored=1).
        The second call with the same eventId is detected by the pre-insert
        dedup check, so stored=0 but the call still succeeds (idempotent).
        """
        event = _make_event()
        r1 = client.post("/telemetry/events", json=_batch([event]))
        assert r1.json()["stored"] == 1

        r2 = client.post("/telemetry/events", json=_batch([event]))
        assert r2.status_code == 200
        assert r2.json()["stored"] == 0

        # Only one row in the DB
        rows = _query_all(telemetry_engine)
        assert len(rows) == 1

    def test_get_not_allowed(self, client):
        """The endpoint is write-only."""
        response = client.get("/telemetry/events")
        assert response.status_code == 405


# ══════════════════════════════════════════════
# Immutability
# ══════════════════════════════════════════════


class TestTelemetryImmutability:
    """Events are immutable once stored — no UPDATE or DELETE paths."""

    def test_no_update_path(self, client, telemetry_engine):
        """There is no UPDATE endpoint for telemetry events."""
        response = client.put("/telemetry/events", json={})
        assert response.status_code == 405

    def test_no_delete_path(self, client, telemetry_engine):
        """There is no DELETE endpoint for telemetry events."""
        response = client.delete("/telemetry/events")
        assert response.status_code == 405
