"""Tests for the telemetry ingestion endpoint.

The telemetry endpoint is deliberately stateless — it logs received
events and returns a count. No database, no auth, no side effects.
"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


# ══════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════


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

    def test_endpoint_exists_and_returns_json(self):
        response = client.post("/telemetry/events", json=_batch([_make_event()]))
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    def test_returns_received_count(self):
        response = client.post(
            "/telemetry/events",
            json=_batch([_make_event(), _make_event()]),
        )
        data = response.json()
        assert data == {"received": 2}

    def test_accepts_single_event(self):
        response = client.post(
            "/telemetry/events",
            json=_batch([_make_event()]),
        )
        assert response.status_code == 200
        assert response.json()["received"] == 1

    def test_accepts_multiple_events(self):
        events = [_make_event() for _ in range(5)]
        response = client.post("/telemetry/events", json=_batch(events))
        assert response.status_code == 200
        assert response.json()["received"] == 5


# ══════════════════════════════════════════════
# Edge cases
# ══════════════════════════════════════════════


class TestTelemetryEdgeCases:
    """Boundary conditions and malformed inputs."""

    def test_empty_batch_returns_zero(self):
        response = client.post("/telemetry/events", json=_batch([]))
        assert response.status_code == 200
        assert response.json()["received"] == 0

    def test_missing_event_type_rejected(self):
        bad = _make_event()
        del bad["event_type"]
        response = client.post("/telemetry/events", json=_batch([bad]))
        assert response.status_code == 422

    def test_invalid_uuid_rejected(self):
        bad = _make_event(eventId="not-a-uuid")
        response = client.post("/telemetry/events", json=_batch([bad]))
        assert response.status_code == 422

    def test_missing_timestamp_rejected(self):
        bad = _make_event()
        del bad["timestamp"]
        response = client.post("/telemetry/events", json=_batch([bad]))
        assert response.status_code == 422

    def test_missing_schema_version_rejected(self):
        bad = _make_event()
        del bad["schemaVersion"]
        response = client.post("/telemetry/events", json=_batch([bad]))
        assert response.status_code == 422

    def test_non_list_events_rejected(self):
        response = client.post(
            "/telemetry/events",
            json={"events": "not_an_array"},
        )
        assert response.status_code == 422

    def test_missing_events_key_rejected(self):
        response = client.post("/telemetry/events", json={})
        assert response.status_code == 422

    def test_batch_with_mixed_valid_invalid_events(self):
        """The endpoint validates per-event, so at least one bad event
        causes the whole batch to be rejected at the model level."""
        valid = _make_event()
        invalid = _make_event(eventId="bad-uuid")
        response = client.post(
            "/telemetry/events",
            json=_batch([valid, invalid]),
        )
        assert response.status_code == 422

    def test_large_properties_accepted(self):
        """Properties is a free-form dict — any JSON object is valid."""
        event = _make_event(
            properties={
                "page": "incidents_list",
                "filters": {"status": "open", "priority": "high"},
            },
        )
        response = client.post("/telemetry/events", json=_batch([event]))
        assert response.status_code == 200
        assert response.json()["received"] == 1


# ══════════════════════════════════════════════
# No persistence guarantee
# ══════════════════════════════════════════════


class TestTelemetryNoPersistence:
    """Verify the endpoint does not write to any database."""

    def test_repeat_same_event_returns_success(self):
        """Stateless — identical payloads are both accepted."""
        event = _make_event()
        r1 = client.post("/telemetry/events", json=_batch([event]))
        r2 = client.post("/telemetry/events", json=_batch([event]))
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json() == r2.json() == {"received": 1}

    def test_get_not_allowed(self):
        """The endpoint is write-only."""
        response = client.get("/telemetry/events")
        assert response.status_code == 405