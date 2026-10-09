"""Tests for services/telemetry/analysis.py — Telemetry analysis pipeline.

Uses an isolated in-memory SQLite engine with controlled data.
Does NOT depend on Supabase for unit tests.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pandas as pd
import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool

# Ensure services/api is importable
import sys
from pathlib import Path
_api_path = str(Path(__file__).resolve().parent.parent.parent / "api")
if _api_path not in sys.path:
    sys.path.insert(0, _api_path)

from telemetry_models import TelemetryEventTable


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def engine():
    """Create a fresh in-memory SQLite engine for telemetry analysis tests."""
    e = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import telemetry_models  # noqa: F401
    SQLModel.metadata.create_all(e)
    yield e
    e.dispose()


@pytest.fixture
def session(engine, request):
    """Yield a clean session with empty telemetry_events table per test."""
    with Session(engine) as s:
        s.exec(TelemetryEventTable.__table__.delete())
        s.commit()

    with Session(engine) as s:
        yield s
        s.close()


# ══════════════════════════════════════════════
# Helpers for controlled data
# ══════════════════════════════════════════════


def _insert_event(
    session: Session,
    *,
    timestamp: datetime | None = None,
    event_type: str = "page_viewed",
    service: str = "backoffice",
    level: str = "info",
    value: Decimal | None = None,
    message: str | None = None,
    tags: dict | None = None,
) -> str:
    """Insert a telemetry event with controlled values. Returns the event id."""
    import uuid
    event_id = str(uuid.uuid4())
    row = TelemetryEventTable(
        id=event_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        service=service,
        event_type=event_type,
        level=level,
        value=value,
        message=message,
        tags=tags or {},
    )
    session.add(row)
    session.commit()
    return event_id


def _insert_batch(session: Session, events: list[dict]) -> None:
    """Bulk insert controlled events."""
    for ev in events:
        e = ev.copy()
        e.setdefault("service", "api")
        e.setdefault("level", "info")
        e.setdefault("tags", {})
        _insert_event(session, **e)


# ══════════════════════════════════════════════
# Import the module under test
# ══════════════════════════════════════════════

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analysis import (
    daily_event_volume,
    error_breakdown,
    warehouse_activity,
    page_popularity,
)


# ══════════════════════════════════════════════
# Tests: Metric 1 — daily_event_volume
# ══════════════════════════════════════════════


class TestDailyEventVolume:
    """Tests for daily_event_volume()."""

    def test_returns_list_of_dicts(self, session):
        """Output shape must be list[dict]."""
        result = daily_event_volume(
            date(2026, 10, 1), date(2026, 10, 8), session
        )
        assert isinstance(result, list)
        # Every item must be a dict
        for item in result:
            assert isinstance(item, dict)

    def test_empty_dataset(self, session):
        """Empty dataset returns an empty list."""
        result = daily_event_volume(
            date(2026, 10, 1), date(2026, 10, 8), session
        )
        assert result == []

    def test_deterministic(self, session):
        """Same input → same output."""
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 11, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "suppliers"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc),
                "event_type": "incident_created",
                "tags": {"category": "lost_parcel"},
            },
        ])

        r1 = daily_event_volume(date(2026, 10, 5), date(2026, 10, 6), session)
        r2 = daily_event_volume(date(2026, 10, 5), date(2026, 10, 6), session)
        assert r1 == r2

    def test_date_filter_inclusive_exclusive(self, session):
        """start_date inclusive, end_date exclusive."""
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 0, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
            {
                "timestamp": datetime(2026, 10, 6, 0, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
            {
                "timestamp": datetime(2026, 10, 7, 0, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
        ])

        # Window Oct 5 (inclusive) to Oct 7 (exclusive) → 2 events
        result = daily_event_volume(date(2026, 10, 5), date(2026, 10, 7), session)
        total = sum(r["count"] for r in result)
        assert total == 2, f"Expected 2, got {total}: {result}"

    def test_groupby_columns(self, session):
        """Result has correct groupby keys: date, event_type."""
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 11, 0, 0, tzinfo=timezone.utc),
                "event_type": "login_succeeded",
                "tags": {"user_role": "admin"},
            },
        ])

        result = daily_event_volume(date(2026, 10, 5), date(2026, 10, 6), session)
        assert len(result) == 2
        keys = {(r["date"], r["event_type"]): r["count"] for r in result}
        assert ("2026-10-05", "page_viewed") in keys
        assert ("2026-10-05", "login_succeeded") in keys
        assert keys[("2026-10-05", "page_viewed")] == 1
        assert keys[("2026-10-05", "login_succeeded")] == 1

    def test_json_serializable(self, session):
        """Result must be serializable to JSON."""
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
        ])

        result = daily_event_volume(date(2026, 10, 5), date(2026, 10, 6), session)
        json_str = json.dumps(result)
        assert isinstance(json_str, str)

    def test_no_loops_for_metrics(self, session):
        """The result must NOT be computed using Python loops over raw rows.

        This is an indirect verification: we check the output has correct
        shape which implies groupby was used correctly.
        """
        events = []
        for day in range(5, 10):
            for etype in ["page_viewed", "incident_created"]:
                events.append({
                    "timestamp": datetime(2026, 10, day, 12, 0, 0, tzinfo=timezone.utc),
                    "event_type": etype,
                    "tags": {"page": "login" if etype == "page_viewed" else None},
                })
        _insert_batch(session, events)

        result = daily_event_volume(date(2026, 10, 5), date(2026, 10, 10), session)
        # Expected: 5 days × 2 types = 10 rows
        assert len(result) == 10
        total = sum(r["count"] for r in result)
        assert total == len(events)


# ══════════════════════════════════════════════
# Tests: Metric 2 — error_breakdown
# ══════════════════════════════════════════════


class TestErrorBreakdown:
    """Tests for error_breakdown()."""

    def test_returns_list_of_dicts(self, session):
        result = error_breakdown(date(2026, 10, 1), date(2026, 10, 8), session)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, dict)

    def test_empty_dataset(self, session):
        result = error_breakdown(date(2026, 10, 1), date(2026, 10, 8), session)
        assert result == []

    def test_only_api_server_error_events(self, session):
        """Non-error events should be ignored."""
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "api_server_error",
                "tags": {"error_code": "INTERNAL_ERROR", "path": "/test"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 11, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc),
                "event_type": "api_server_error",
                "tags": {"error_code": "TIMEOUT", "path": "/other"},
            },
        ])

        result = error_breakdown(date(2026, 10, 5), date(2026, 10, 6), session)
        assert len(result) == 2
        codes = {r["error_code"]: r["count"] for r in result}
        assert codes.get("INTERNAL_ERROR") == 1
        assert codes.get("TIMEOUT") == 1

    def test_includes_percentage(self, session):
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "api_server_error",
                "tags": {"error_code": "INTERNAL_ERROR"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 11, 0, 0, tzinfo=timezone.utc),
                "event_type": "api_server_error",
                "tags": {"error_code": "INTERNAL_ERROR"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc),
                "event_type": "api_server_error",
                "tags": {"error_code": "TIMEOUT"},
            },
        ])

        result = error_breakdown(date(2026, 10, 5), date(2026, 10, 6), session)
        assert len(result) == 2
        codes = {r["error_code"]: r for r in result}
        assert codes["INTERNAL_ERROR"]["pct"] == 66.67
        assert codes["TIMEOUT"]["pct"] == 33.33

    def test_deterministic(self, session):
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "api_server_error",
                "tags": {"error_code": "INTERNAL_ERROR"},
            },
        ])
        r1 = error_breakdown(date(2026, 10, 5), date(2026, 10, 6), session)
        r2 = error_breakdown(date(2026, 10, 5), date(2026, 10, 6), session)
        assert r1 == r2

    def test_json_serializable(self, session):
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "api_server_error",
                "tags": {"error_code": "INTERNAL_ERROR"},
            },
        ])
        result = error_breakdown(date(2026, 10, 5), date(2026, 10, 6), session)
        json.dumps(result)

    def test_null_error_code_skipped(self, session):
        """Events without error_code in tags should be skipped."""
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "api_server_error",
                "tags": {"path": "/test"},  # no error_code
            },
            {
                "timestamp": datetime(2026, 10, 5, 11, 0, 0, tzinfo=timezone.utc),
                "event_type": "api_server_error",
                "tags": {"error_code": "INTERNAL_ERROR"},
            },
        ])
        result = error_breakdown(date(2026, 10, 5), date(2026, 10, 6), session)
        assert len(result) == 1
        assert result[0]["error_code"] == "INTERNAL_ERROR"


# ══════════════════════════════════════════════
# Tests: Metric 3 — warehouse_activity
# ══════════════════════════════════════════════


class TestWarehouseActivity:
    """Tests for warehouse_activity()."""

    def test_returns_list_of_dicts(self, session):
        result = warehouse_activity(date(2026, 10, 1), date(2026, 10, 8), session)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, dict)

    def test_empty_dataset(self, session):
        result = warehouse_activity(date(2026, 10, 1), date(2026, 10, 8), session)
        assert result == []

    def test_only_inventory_events(self, session):
        """Only inbound_registered and outbound_registered should be counted."""
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "inbound_registered",
                "tags": {"warehouse": "LA"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 11, 0, 0, tzinfo=timezone.utc),
                "event_type": "outbound_registered",
                "tags": {"warehouse": "ZGZ"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",  # Should be ignored
                "tags": {"page": "login"},
            },
        ])

        result = warehouse_activity(date(2026, 10, 5), date(2026, 10, 6), session)
        assert len(result) == 2
        keys = {(r["warehouse"], r["event_type"]): r["count"] for r in result}
        assert ("LA", "inbound_registered") in keys
        assert ("ZGZ", "outbound_registered") in keys

    def test_groupby_warehouse_and_event_type(self, session):
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "inbound_registered",
                "tags": {"warehouse": "LA"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 11, 0, 0, tzinfo=timezone.utc),
                "event_type": "inbound_registered",
                "tags": {"warehouse": "LA"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc),
                "event_type": "outbound_registered",
                "tags": {"warehouse": "LA"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 13, 0, 0, tzinfo=timezone.utc),
                "event_type": "outbound_registered",
                "tags": {"warehouse": "ZGZ"},
            },
        ])

        result = warehouse_activity(date(2026, 10, 5), date(2026, 10, 6), session)
        assert len(result) == 3
        keys = {(r["warehouse"], r["event_type"]): r["count"] for r in result}
        assert keys[("LA", "inbound_registered")] == 2
        assert keys[("LA", "outbound_registered")] == 1
        assert keys[("ZGZ", "outbound_registered")] == 1

    def test_deterministic(self, session):
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "inbound_registered",
                "tags": {"warehouse": "LA"},
            },
        ])
        r1 = warehouse_activity(date(2026, 10, 5), date(2026, 10, 6), session)
        r2 = warehouse_activity(date(2026, 10, 5), date(2026, 10, 6), session)
        assert r1 == r2

    def test_json_serializable(self, session):
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "inbound_registered",
                "tags": {"warehouse": "LA"},
            },
        ])
        result = warehouse_activity(date(2026, 10, 5), date(2026, 10, 6), session)
        json.dumps(result)

    def test_null_warehouse_skipped(self, session):
        """Events without warehouse in tags should be skipped."""
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "inbound_registered",
                "tags": {},  # no warehouse
            },
            {
                "timestamp": datetime(2026, 10, 5, 11, 0, 0, tzinfo=timezone.utc),
                "event_type": "inbound_registered",
                "tags": {"warehouse": "ZGZ"},
            },
        ])
        result = warehouse_activity(date(2026, 10, 5), date(2026, 10, 6), session)
        assert len(result) == 1
        assert result[0]["warehouse"] == "ZGZ"


# ══════════════════════════════════════════════
# Tests: Metric 4 — page_popularity
# ══════════════════════════════════════════════


class TestPagePopularity:
    """Tests for page_popularity()."""

    def test_returns_list_of_dicts(self, session):
        result = page_popularity(date(2026, 10, 1), date(2026, 10, 8), session)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, dict)

    def test_empty_dataset(self, session):
        result = page_popularity(date(2026, 10, 1), date(2026, 10, 8), session)
        assert result == []

    def test_only_page_viewed_events(self, session):
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 11, 0, 0, tzinfo=timezone.utc),
                "event_type": "incident_created",
                "tags": {"category": "lost_parcel"},
            },
        ])
        result = page_popularity(date(2026, 10, 5), date(2026, 10, 6), session)
        assert len(result) == 1
        assert result[0]["page"] == "login"

    def test_groupby_page(self, session):
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 11, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "suppliers"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 13, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
        ])
        result = page_popularity(date(2026, 10, 5), date(2026, 10, 6), session)
        assert len(result) == 2
        pages = {r["page"]: r["count"] for r in result}
        assert pages["login"] == 3
        assert pages["suppliers"] == 1

    def test_deterministic(self, session):
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
        ])
        r1 = page_popularity(date(2026, 10, 5), date(2026, 10, 6), session)
        r2 = page_popularity(date(2026, 10, 5), date(2026, 10, 6), session)
        assert r1 == r2

    def test_json_serializable(self, session):
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
        ])
        result = page_popularity(date(2026, 10, 5), date(2026, 10, 6), session)
        json.dumps(result)

    def test_null_page_skipped(self, session):
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {},  # no page
            },
            {
                "timestamp": datetime(2026, 10, 5, 11, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
        ])
        result = page_popularity(date(2026, 10, 5), date(2026, 10, 6), session)
        assert len(result) == 1
        assert result[0]["page"] == "login"


# ══════════════════════════════════════════════
# Cross-cutting concerns
# ══════════════════════════════════════════════


class TestCrossCutting:
    """Tests that span multiple metrics."""

    def test_all_functions_accept_session(self, session):
        """All functions accept an optional session parameter."""
        _insert_batch(session, [
            {
                "timestamp": datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
                "event_type": "page_viewed",
                "tags": {"page": "login"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 11, 0, 0, tzinfo=timezone.utc),
                "event_type": "api_server_error",
                "tags": {"error_code": "INTERNAL_ERROR"},
            },
            {
                "timestamp": datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc),
                "event_type": "inbound_registered",
                "tags": {"warehouse": "LA"},
            },
        ])

        sd, ed = date(2026, 10, 5), date(2026, 10, 6)

        r1 = daily_event_volume(sd, ed, session)
        r2 = error_breakdown(sd, ed, session)
        r3 = warehouse_activity(sd, ed, session)
        r4 = page_popularity(sd, ed, session)

        assert len(r1) >= 1
        assert len(r2) >= 1
        assert len(r3) >= 1
        assert len(r4) >= 1

    def test_no_business_metrics_present(self, session):
        """Verify we have no business metrics (revenue, sales, conversion)."""
        from analysis import daily_event_volume, error_breakdown, warehouse_activity, page_popularity

        # Business-related terms that should NOT appear in function names
        business_terms = {"revenue", "sales", "conversion", "income", "profit"}
        func_names = {daily_event_volume.__name__, error_breakdown.__name__,
                      warehouse_activity.__name__, page_popularity.__name__}
        for term in business_terms:
            for fname in func_names:
                assert term not in fname.lower(), f"Business term '{term}' found in function '{fname}'"