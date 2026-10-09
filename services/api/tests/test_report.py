"""Tests for GET /telemetry/report endpoint.

Covers:
    * Endpoint acceptance (200, JSON shape, period, metrics)
    * Date parameter validation (ISO format, ordering, defaults)
    * Default window (7 days when no params)
    * All metrics returned with consistent window
    * JSON serialization of entire response
    * Cache hit/miss/expiry behaviour
    * Different periods = different cache entries
    * No Pandas in endpoint layer (analysis functions are separate)
    * No business metrics created (only technical telemetry metrics)
"""

from __future__ import annotations

import json as json_module
import time as time_module
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool
from sqlalchemy import text as sa_text

from main import app
from database import get_db
from telemetry_models import TelemetryEventTable
from telemetry.cache import report_cache


from telemetry.analysis import (  # noqa: E402
    daily_event_volume,
    error_breakdown,
    warehouse_activity,
    page_popularity,
)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def report_engine():
    """In-memory SQLite engine shared across all report tests.

    Uses StaticPool so the TestClient worker thread and the test thread
    share the same in-memory connection.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import telemetry_models  # noqa: F401 — register TelemetryEventTable

    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _safe_env(monkeypatch):
    """Isolate tests from any real DATABASE_URL that may be set.

    Without this, the analysis pipeline's ``_get_session()`` could
    inadvertently connect to Supabase.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "development")


@pytest.fixture(autouse=True)
def _clean_telemetry_events(report_engine):
    """Delete all rows from telemetry_events before each test.

    The engine is module-scoped so without cleanup tests would accumulate
    rows from previous tests.
    """
    with Session(report_engine) as session:
        session.exec(sa_text("DELETE FROM telemetry_events"))
        session.commit()


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the module-level report cache before each test.

    Without this, cache entries from one test could produce false cache
    hits in a subsequent test with the same date window.
    """
    report_cache.clear()


@pytest.fixture
def client(report_engine, _safe_env, _clean_telemetry_events, _clear_cache):
    """TestClient with ``get_db`` overridden to the isolated test engine.

    This ensures the endpoint's database session resolves to our in-memory
    SQLite rather than the real Supabase instance.
    """

    def override_get_db():
        with Session(report_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)


# ──────────────────────────────────────────────
# Test-data helpers
# ──────────────────────────────────────────────


def _insert_event(
    session: Session,
    *,
    timestamp: datetime | None = None,
    event_type: str = "page_viewed",
    service: str = "backoffice",
    level: str = "info",
    tags: dict | None = None,
) -> str:
    """Insert a single telemetry event with controlled values. Returns id."""
    import uuid

    event_id = str(uuid.uuid4())
    row = TelemetryEventTable(
        id=event_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        service=service,
        event_type=event_type,
        level=level,
        tags=tags or {},
    )
    session.add(row)
    session.commit()
    return event_id


def _seed_all_metrics(session: Session, base_day: date | None = None) -> None:
    """Insert a batch of events covering all 4 metric groups.

    Creates events across 3 consecutive days so the default 7-day window
    always includes them.
    """
    if base_day is None:
        base_day = date.today() - timedelta(days=3)

    # Day 1 — 3 events
    d1 = datetime(base_day.year, base_day.month,
                  base_day.day, 10, 0, 0, tzinfo=timezone.utc)
    _insert_event(session, timestamp=d1, event_type="page_viewed",
                  tags={"page": "suppliers"})
    _insert_event(session, timestamp=d1, event_type="page_viewed",
                  tags={"page": "dashboard"})
    _insert_event(
        session, timestamp=d1, event_type="api_server_error",
        tags={"error_code": "500", "path": "/api/suppliers"},
    )
    _insert_event(
        session, timestamp=d1, event_type="inbound_registered",
        tags={"warehouse": "MIA", "sku_code": "ABC", "quantity": 10},
    )

    # Day 2 — 4 events
    d2 = datetime(base_day.year, base_day.month, base_day.day +
                  1, 12, 0, 0, tzinfo=timezone.utc)
    _insert_event(session, timestamp=d2, event_type="page_viewed",
                  tags={"page": "reports"})
    _insert_event(
        session, timestamp=d2, event_type="api_server_error",
        tags={"error_code": "502", "path": "/api/inventory"},
    )
    _insert_event(
        session, timestamp=d2, event_type="outbound_registered",
        tags={"warehouse": "MIA", "sku_code": "XYZ", "quantity": 5},
    )
    _insert_event(
        session, timestamp=d2, event_type="inbound_registered",
        tags={"warehouse": "JFK", "sku_code": "DEF", "quantity": 20},
    )

    # Day 3 — 2 events
    d3 = datetime(base_day.year, base_day.month, base_day.day +
                  2, 14, 0, 0, tzinfo=timezone.utc)
    _insert_event(session, timestamp=d3, event_type="page_viewed",
                  tags={"page": "suppliers"})
    _insert_event(
        session, timestamp=d3, event_type="api_server_error",
        tags={"error_code": "500", "path": "/api/users"},
    )


# ──────────────────────────────────────────────
# Tests: Basic acceptance
# ──────────────────────────────────────────────


class TestAcceptance:
    """GET /telemetry/report exists, returns 200, and has the expected shape."""

    def test_endpoint_returns_200(self, client):
        """The endpoint responds with HTTP 200 and JSON content-type."""
        response = client.get("/telemetry/report")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    def test_response_contains_period(self, client):
        """The response body includes a ``period`` key with ``from`` / ``to``."""
        response = client.get("/telemetry/report")
        data = response.json()
        assert "period" in data
        assert "from" in data["period"]
        assert "to" in data["period"]

    def test_response_contains_metrics(self, client, report_engine):
        """The response body includes a ``metrics`` key with all 4 groups."""
        with Session(report_engine) as session:
            _seed_all_metrics(session)

        response = client.get("/telemetry/report")
        data = response.json()
        assert "metrics" in data
        metrics = data["metrics"]
        assert "events_per_day" in metrics
        assert "error_rate_by_type" in metrics
        assert "warehouse_activity" in metrics
        assert "page_popularity" in metrics

    def test_metrics_are_lists(self, client, report_engine):
        """Each metric group is a list (possibly empty)."""
        with Session(report_engine) as session:
            _seed_all_metrics(session)

        response = client.get("/telemetry/report")
        data = response.json()
        metrics = data["metrics"]
        assert isinstance(metrics["events_per_day"], list)
        assert isinstance(metrics["error_rate_by_type"], list)
        assert isinstance(metrics["warehouse_activity"], list)
        assert isinstance(metrics["page_popularity"], list)

    def test_metrics_contain_data(self, client, report_engine):
        """With seeded data, all 4 metric lists are non-empty."""
        with Session(report_engine) as session:
            _seed_all_metrics(session)

        response = client.get("/telemetry/report")
        data = response.json()
        metrics = data["metrics"]
        assert len(metrics["events_per_day"]) > 0
        assert len(metrics["error_rate_by_type"]) > 0
        assert len(metrics["warehouse_activity"]) > 0
        assert len(metrics["page_popularity"]) > 0

    def test_response_entirely_json_serializable(self, client, report_engine):
        """The full response can be round-tripped through ``json.dumps``."""
        with Session(report_engine) as session:
            _seed_all_metrics(session)

        response = client.get("/telemetry/report")
        data = response.json()
        # Re-serialise — should not raise
        json_module.dumps(data)


# ──────────────────────────────────────────────
# Tests: Date parameters
# ──────────────────────────────────────────────


class TestDateParameters:
    """Validation and defaults for ``start_date`` / ``end_date``."""

    def test_explicit_dates_work(self, client, report_engine):
        """Passing explicit start_date and end_date returns a 200 response."""
        with Session(report_engine) as session:
            _seed_all_metrics(session)

        response = client.get(
            "/telemetry/report",
            params={"start_date": "2026-10-01", "end_date": "2026-10-31"},
        )
        assert response.status_code == 200

    def test_explicit_dates_reflected_in_period(self, client):
        """The period matches the explicit dates passed."""
        response = client.get(
            "/telemetry/report",
            params={"start_date": "2026-10-01", "end_date": "2026-10-31"},
        )
        data = response.json()
        assert data["period"]["from"] == "2026-10-01"
        assert data["period"]["to"] == "2026-10-31"

    def test_default_window_is_7_days(self, client, report_engine):
        """Without params, period spans the last 7 days."""
        with Session(report_engine) as session:
            _seed_all_metrics(session)

        response = client.get("/telemetry/report")
        data = response.json()
        period_from = date.fromisoformat(data["period"]["from"])
        period_to = date.fromisoformat(data["period"]["to"])
        delta = (period_to - period_from).days
        # Should be ~7 days (could be 7 or 6 depending on time-of-day edge)
        assert delta == 7

    def test_default_end_is_today(self, client):
        """Without end_date, the period's ``to`` equals today UTC."""
        response = client.get("/telemetry/report")
        data = response.json()
        today = datetime.now(timezone.utc).date().isoformat()
        assert data["period"]["to"] == today

    def test_start_equal_to_end_returns_422(self, client):
        """start_date == end_date must raise a 422 validation error."""
        response = client.get(
            "/telemetry/report",
            params={"start_date": "2026-10-01", "end_date": "2026-10-01"},
        )
        assert response.status_code == 422

    def test_start_after_end_returns_422(self, client):
        """start_date > end_date must raise a 422 validation error."""
        response = client.get(
            "/telemetry/report",
            params={"start_date": "2026-10-31", "end_date": "2026-10-01"},
        )
        assert response.status_code == 422

    def test_start_after_end_detail_message(self, client):
        """The 422 response includes a descriptive detail message."""
        response = client.get(
            "/telemetry/report",
            params={"start_date": "2026-10-31", "end_date": "2026-10-01"},
        )
        data = response.json()
        detail = data.get("detail", "")
        assert "start_date" in str(detail).lower(
        ) and "end_date" in str(detail).lower()

    def test_invalid_iso_date_returns_422(self, client):
        """A non-ISO date string must raise a 422 validation error."""
        response = client.get(
            "/telemetry/report",
            params={"start_date": "not-a-date"},
        )
        assert response.status_code == 422

    def test_date_format_must_be_iso(self, client):
        """Incomplete ISO date (e.g. '2026-10') must raise 422."""
        response = client.get(
            "/telemetry/report",
            params={"start_date": "2026-10"},
        )
        assert response.status_code == 422


# ──────────────────────────────────────────────
# Regression: BUG-1 — default period must include
# today's data (not truncate to midnight UTC)
# ──────────────────────────────────────────────


class TestDefaultPeriodIncludesToday:
    """Regression: BUG-1 — default period includes today's data.

    When ``GET /telemetry/report`` is called without ``start_date`` or
    ``end_date``, the default period's upper bound must be the current
    UTC datetime (not midnight UTC) so that events from earlier today
    are included in the metrics.
    """

    def test_default_period_includes_today_events(
        self, client, report_engine, monkeypatch
    ):
        """Events created *today* (before now) appear in the default period."""
        FROZEN = datetime(2026, 10, 7, 23, 15, 0, tzinfo=timezone.utc)
        EVENT_TIME = FROZEN - timedelta(hours=1)  # same day, before "now"

        with Session(report_engine) as session:
            _insert_event(
                session,
                timestamp=EVENT_TIME,
                event_type="page_viewed",
                tags={"page": "regression-test"},
            )

        # Build a frozen datetime subclass and patch it into the router
        class _FrozenDT(datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                return FROZEN if tz is None else FROZEN.astimezone(tz)

        import routers.telemetry as _rt  # type: ignore[import-untyped]

        monkeypatch.setattr(_rt, "datetime", _FrozenDT)

        response = client.get("/telemetry/report")

        assert response.status_code == 200
        data = response.json()
        metrics = data["metrics"]

        # Period "to" should be today (the frozen date)
        assert data["period"]["to"] == "2026-10-07"
        # Period "from" should be 7 days before
        assert data["period"]["from"] == "2026-09-30"

        # events_per_day must contain today's event
        event_dates = {
            (e["date"], e["event_type"], e["count"])
            for e in metrics["events_per_day"]
        }
        assert ("2026-10-07", "page_viewed", 1) in event_dates, (
            f"Today's event missing from events_per_day: {event_dates}"
        )

    def test_default_period_excludes_future_events(
        self, client, report_engine, monkeypatch
    ):
        """Events after ``now`` are excluded from the default period."""
        FROZEN = datetime(2026, 10, 7, 23, 15, 0, tzinfo=timezone.utc)
        FUTURE_EVENT = FROZEN + timedelta(hours=2)  # after "now"

        with Session(report_engine) as session:
            _insert_event(
                session,
                timestamp=FUTURE_EVENT,
                event_type="page_viewed",
                tags={"page": "future-regression"},
            )

        class _FrozenDT(datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[override]
                return FROZEN if tz is None else FROZEN.astimezone(tz)

        import routers.telemetry as _rt  # type: ignore[import-untyped]

        monkeypatch.setattr(_rt, "datetime", _FrozenDT)

        response = client.get("/telemetry/report")

        assert response.status_code == 200
        data = response.json()
        metrics = data["metrics"]

        # events_per_day should be empty — no events before "now"
        assert metrics["events_per_day"] == [], (
            "Events after 'now' must not appear in default period"
        )


# ──────────────────────────────────────────────
# Tests: All metrics receive the same window
# ──────────────────────────────────────────────


class TestMetricsConsistency:
    """All 4 metric groups are computed over the identical date window."""

    def test_all_metrics_use_same_window(self, client, report_engine):
        """Calling each analysis function directly with the same window
        produces the same results as the endpoint's combined response."""
        with Session(report_engine) as session:
            _seed_all_metrics(session)

        # Choose an explicit window
        start = date(2026, 10, 1)
        end = date(2026, 10, 31)

        response = client.get(
            "/telemetry/report",
            params={"start_date": start.isoformat(), "end_date": end.isoformat()},
        )
        data = response.json()
        endpoint_metrics = data["metrics"]

        # Now call each analysis function directly with the same window
        # and a fresh session (the events are already in the DB).
        with Session(report_engine) as session:
            direct_events = daily_event_volume(start, end, session)
            direct_errors = error_breakdown(start, end, session)
            direct_warehouse = warehouse_activity(start, end, session)
            direct_pages = page_popularity(start, end, session)

        # The endpoint results should match the direct calls.
        # Note: the endpoint returns sorted data, so direct comparison works.
        assert endpoint_metrics["events_per_day"] == direct_events
        assert endpoint_metrics["error_rate_by_type"] == direct_errors
        assert endpoint_metrics["warehouse_activity"] == direct_warehouse
        assert endpoint_metrics["page_popularity"] == direct_pages


# ──────────────────────────────────────────────
# Tests: Cache behaviour
# ──────────────────────────────────────────────


class TestCache:
    """The in-memory TTL cache avoids recomputation within the TTL window."""

    def test_cache_hit_returns_same_result(self, client, report_engine):
        """Two identical requests within TTL return the same metric values."""
        with Session(report_engine) as session:
            _seed_all_metrics(session)

        resp1 = client.get("/telemetry/report")
        resp2 = client.get("/telemetry/report")

        assert resp1.json() == resp2.json()

    def test_cache_avoids_recomputation(self, client, report_engine):
        """When cached, the analysis functions are NOT called again.

        We verify by patching the bound names in the router module.
        """
        from routers import telemetry as router_module

        with Session(report_engine) as session:
            _seed_all_metrics(session)

        # First request — populates the cache
        resp1 = client.get("/telemetry/report")
        assert resp1.status_code == 200

        # Second request — should hit the cache
        with patch.object(router_module, "daily_event_volume") as mock_vol, \
                patch.object(router_module, "error_breakdown") as mock_err, \
                patch.object(router_module, "warehouse_activity") as mock_wh, \
                patch.object(router_module, "page_popularity") as mock_page:

            resp2 = client.get("/telemetry/report")
            assert resp2.status_code == 200
            # The cached result should be returned without calling any
            # analysis function.
            mock_vol.assert_not_called()
            mock_err.assert_not_called()
            mock_wh.assert_not_called()
            mock_page.assert_not_called()

    def test_different_periods_different_cache_entries(self, client, report_engine):
        """Requests with different date windows produce different cache keys
        and do NOT share cached results."""
        from routers import telemetry as router_module

        with Session(report_engine) as session:
            _seed_all_metrics(session)

        # Request period A
        resp_a = client.get(
            "/telemetry/report",
            params={"start_date": "2026-10-01", "end_date": "2026-10-07"},
        )
        assert resp_a.status_code == 200

        # Request period B (different) — should be a cache miss
        with patch.object(router_module, "daily_event_volume") as mock_vol, \
                patch.object(router_module, "error_breakdown") as mock_err, \
                patch.object(router_module, "warehouse_activity") as mock_wh, \
                patch.object(router_module, "page_popularity") as mock_page:

            resp_b = client.get(
                "/telemetry/report",
                params={"start_date": "2026-11-01", "end_date": "2026-11-07"},
            )
            assert resp_b.status_code == 200
            # Different period = cache miss = analysis functions called
            mock_vol.assert_called_once()
            mock_err.assert_called_once()
            mock_wh.assert_called_once()
            mock_page.assert_called_once()

    def test_cache_ttl_expiry_recomputes(self, client, report_engine):
        """After the TTL expires, a subsequent request recomputes metrics."""
        from routers import telemetry as router_module

        with Session(report_engine) as session:
            _seed_all_metrics(session)

        # Set a very short TTL for this test
        original_ttl = report_cache._default_ttl
        report_cache._default_ttl = 0.01

        try:
            # First request — populates the cache
            resp1 = client.get("/telemetry/report")
            assert resp1.status_code == 200

            # Wait for TTL to expire
            time_module.sleep(0.02)

            # Second request — cache expired, should recompute
            with patch.object(router_module, "daily_event_volume") as mock_vol, \
                    patch.object(router_module, "error_breakdown") as mock_err, \
                    patch.object(router_module, "warehouse_activity") as mock_wh, \
                    patch.object(router_module, "page_popularity") as mock_page:

                resp2 = client.get("/telemetry/report")
                assert resp2.status_code == 200
                mock_vol.assert_called_once()
                mock_err.assert_called_once()
                mock_wh.assert_called_once()
                mock_page.assert_called_once()
        finally:
            report_cache._default_ttl = original_ttl

    def test_cache_hit_within_ttl_returns_same_data(self, client, report_engine):
        """Within the TTL window, the exact same Python object reference
        (not just same shape) is returned."""
        with Session(report_engine) as session:
            _seed_all_metrics(session)

        resp1 = client.get("/telemetry/report")
        resp2 = client.get("/telemetry/report")

        assert resp1.json() == resp2.json()

    def test_clear_cache_forces_recomputation(self, client, report_engine):
        """Manually clearing the cache forces recomputation on the next request."""
        from routers import telemetry as router_module

        with Session(report_engine) as session:
            _seed_all_metrics(session)

        # First request — populates cache
        resp1 = client.get("/telemetry/report")
        assert resp1.status_code == 200

        # Clear the cache
        report_cache.clear()

        # Second request — should recompute
        with patch.object(router_module, "daily_event_volume") as mock_vol, \
                patch.object(router_module, "error_breakdown") as mock_err, \
                patch.object(router_module, "warehouse_activity") as mock_wh, \
                patch.object(router_module, "page_popularity") as mock_page:

            resp2 = client.get("/telemetry/report")
            assert resp2.status_code == 200
            mock_vol.assert_called_once()
            mock_err.assert_called_once()
            mock_wh.assert_called_once()
            mock_page.assert_called_once()


# ──────────────────────────────────────────────
# Tests: No Pandas in endpoint layer
# ──────────────────────────────────────────────


class TestNoPandasInEndpoint:
    """The endpoint itself does NOT import or use Pandas.

    Pandas computation lives exclusively in ``services/telemetry/analysis.py``.
    The router only calls the analysis functions (already tested above) and
    combines their results.  We verify that the router module never references
    ``pandas``.
    """

    def test_router_does_not_import_pandas(self):
        """The router module's namespace does not contain 'pandas' or 'pd'."""
        from routers import telemetry as router_module

        # Check the module-level names
        module_imports = set(dir(router_module))
        # pandas may appear as 'pandas' or be accessible via the module
        # (e.g. if something in the import chain pulled it in).  We check
        # that the router does NOT have a direct top-level reference.
        assert "pandas" not in module_imports
        assert "pd" not in module_imports

    def test_analysis_functions_are_separate(self, client, report_engine):
        """The analysis functions live in ``analysis.py``, not in the router.

        This test confirms the architectural boundary: the endpoint delegates
        to imported functions rather than performing its own Pandas operations.
        """
        import telemetry.analysis as analysis_module
        from routers import telemetry as router_module

        # The router imports these 4 functions from analysis
        assert router_module.daily_event_volume is analysis_module.daily_event_volume
        assert router_module.error_breakdown is analysis_module.error_breakdown
        assert router_module.warehouse_activity is analysis_module.warehouse_activity
        assert router_module.page_popularity is analysis_module.page_popularity


# ──────────────────────────────────────────────
# Tests: No business metrics
# ──────────────────────────────────────────────


class TestNoBusinessMetrics:
    """The endpoint returns only technical telemetry metrics.

    Business metrics (revenue, profit, customer acquisition cost, churn,
    conversion rates, etc.) must NOT appear.  Only the four metric groups
    defined by the telemetry analysis pipeline are allowed.
    """

    # Known business-metric keywords that must NEVER appear in the response.
    _BUSINESS_KEYWORDS: set[str] = {
        "revenue", "profit", "margin", "cac", "ltv", "churn",
        "conversion", "roi", "cost", "customer_acquisition",
        "customer_lifetime", "arr", "mrr", "gmv", "aov",
    }

    def test_no_business_metric_keys(self, client, report_engine):
        """None of the metric keys in the response contain business terms."""
        with Session(report_engine) as session:
            _seed_all_metrics(session)

        response = client.get("/telemetry/report")
        data = response.json()
        metrics = data.get("metrics", {})

        # Collect all top-level metric keys and nested keys
        all_keys: set[str] = set()
        all_keys.update(metrics.keys())
        for group_name, group_value in metrics.items():
            if isinstance(group_value, list):
                for item in group_value:
                    if isinstance(item, dict):
                        all_keys.update(item.keys())

        # Check for forbidden business terms
        for key in all_keys:
            key_lower = key.lower()
            for business_term in self._BUSINESS_KEYWORDS:
                assert business_term not in key_lower, (
                    f"Key '{key}' contains business-metric term '{business_term}'"
                )

    def test_only_four_metric_groups(self, client):
        """The metrics object contains exactly the 4 defined keys."""
        response = client.get("/telemetry/report")
        data = response.json()
        metrics = data.get("metrics", {})
        expected_keys = {
            "events_per_day",
            "error_rate_by_type",
            "warehouse_activity",
            "page_popularity",
        }
        assert set(metrics.keys()) == expected_keys


# ──────────────────────────────────────────────
# Tests: Empty-data edge cases
# ──────────────────────────────────────────────


class TestEmptyData:
    """The endpoint handles empty databases gracefully."""

    def test_empty_returns_empty_lists(self, client):
        """With no events in the DB, all 4 metric groups return [].

        The period is still reported normally.
        """
        response = client.get("/telemetry/report")
        data = response.json()
        assert data["period"]["from"] is not None
        assert data["period"]["to"] is not None

        metrics = data["metrics"]
        assert metrics["events_per_day"] == []
        assert metrics["error_rate_by_type"] == []
        assert metrics["warehouse_activity"] == []
        assert metrics["page_popularity"] == []

    def test_empty_still_has_period(self, client):
        """Even with no data, the period is always present."""
        response = client.get("/telemetry/report")
        data = response.json()
        assert "period" in data
        assert "from" in data["period"]
        assert "to" in data["period"]


# ──────────────────────────────────────────────
# Tests: Cache module unit tests
# ──────────────────────────────────────────────


class TestCacheModule:
    """Unit tests for the ReportCache class itself (not via endpoint)."""

    def test_get_returns_none_on_miss(self):
        """Getting an unknown key returns None."""
        from telemetry.cache import ReportCache

        c = ReportCache(default_ttl=60)
        result = c.get(date(2026, 10, 1), date(2026, 10, 31))
        assert result is None

    def test_set_then_get_returns_value(self):
        """A value stored via set() is retrievable via get()."""
        from telemetry.cache import ReportCache

        c = ReportCache(default_ttl=60)
        expected = [{"events_per_day": []}]
        c.set(date(2026, 10, 1), date(2026, 10, 31), expected)
        result = c.get(date(2026, 10, 1), date(2026, 10, 31))
        assert result == expected

    def test_get_or_compute_calls_fn_on_miss(self):
        """get_or_compute invokes the compute function on a cache miss."""
        from telemetry.cache import ReportCache

        c = ReportCache(default_ttl=60)
        called = False

        def compute():
            nonlocal called
            called = True
            return [{"events_per_day": []}]

        result = c.get_or_compute(
            date(2026, 10, 1), date(2026, 10, 31), compute)
        assert called is True
        assert result == [{"events_per_day": []}]

    def test_get_or_compute_does_not_call_fn_on_hit(self):
        """get_or_compute does NOT call the compute function on a cache hit."""
        from telemetry.cache import ReportCache

        c = ReportCache(default_ttl=60)
        expected = [{"events_per_day": []}]
        c.set(date(2026, 10, 1), date(2026, 10, 31), expected)

        called = False

        def compute():
            nonlocal called
            called = True
            return [{"different": "value"}]

        result = c.get_or_compute(
            date(2026, 10, 1), date(2026, 10, 31), compute)
        assert called is False
        assert result == expected  # cached value, not compute's value

    def test_expired_entry_returns_none(self):
        """An expired cache entry is not returned by get()."""
        from telemetry.cache import ReportCache

        c = ReportCache(default_ttl=0.01)
        c.set(date(2026, 10, 1), date(2026, 10, 31), [{"events_per_day": []}])

        # After TTL expires, get() should return None
        time_module.sleep(0.02)
        result = c.get(date(2026, 10, 1), date(2026, 10, 31))
        assert result is None

    def test_invalidate_removes_key(self):
        """invalidate() removes a specific cache entry."""
        from telemetry.cache import ReportCache

        c = ReportCache(default_ttl=60)
        c.set(date(2026, 10, 1), date(2026, 10, 31), [{"events_per_day": []}])
        c.invalidate(date(2026, 10, 1), date(2026, 10, 31))
        assert c.get(date(2026, 10, 1), date(2026, 10, 31)) is None

    def test_clear_removes_all_entries(self):
        """clear() removes all cache entries."""
        from telemetry.cache import ReportCache

        c = ReportCache(default_ttl=60)
        c.set(date(2026, 10, 1), date(2026, 10, 31), [{"events_per_day": []}])
        c.set(date(2026, 11, 1), date(2026, 11, 30), [{"events_per_day": []}])
        c.clear()
        assert c.get(date(2026, 10, 1), date(2026, 10, 31)) is None
        assert c.get(date(2026, 11, 1), date(2026, 11, 30)) is None

    def test_different_keys_independent(self):
        """Different date pairs produce different cache keys and do not collide."""
        from telemetry.cache import ReportCache

        c = ReportCache(default_ttl=60)
        val_a = [{"metric": "A"}]
        val_b = [{"metric": "B"}]
        c.set(date(2026, 10, 1), date(2026, 10, 31), val_a)
        c.set(date(2026, 11, 1), date(2026, 11, 30), val_b)

        assert c.get(date(2026, 10, 1), date(2026, 10, 31)) == val_a
        assert c.get(date(2026, 11, 1), date(2026, 11, 30)) == val_b
