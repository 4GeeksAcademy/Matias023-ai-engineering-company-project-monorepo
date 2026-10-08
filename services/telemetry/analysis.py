"""Telemetry event analysis pipeline with Pandas.

Pipeline order (per specification):
    SQL → Pandas → convert types → groupby → agg → list[dict]

Each function:
  1. Loads only necessary rows from SQL within the date window
  2. Filters timestamp and event_type in SQL when applicable
  3. Refines data with Pandas
  4. Converts timestamp to datetime UTC before any temporal grouping
  5. Groups with Pandas groupby()
  6. Aggregates with Pandas agg() / count() / sum() / mean()
  7. Returns a list of dicts serializable to JSON
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

# Ensure services/api is importable (same pattern as scripts/migrate_telemetry_pg.py)
_api_path = str(Path(__file__).resolve().parent.parent / "api")
if _api_path not in sys.path:
    sys.path.insert(0, _api_path)

from database import get_engine
from sqlmodel import Session, select
from telemetry_models import TelemetryEventTable


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────


def _get_session() -> Session:
    """Create a new SQLModel session for database queries."""
    engine = get_engine()
    return Session(engine)


def _safe_tags(tags: Any) -> dict:
    """Return a dict from tags, handling None and non-dict values."""
    if isinstance(tags, dict):
        return tags
    return {}


def _date_to_dt(d: date) -> datetime:
    """Convert a date or datetime to a UTC datetime for SQL querying.

    If *d* is already a ``datetime`` (timezone-aware), it is returned as-is.
    If *d* is a plain ``date``, it is converted to midnight UTC.
    """
    if isinstance(d, datetime):
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _serialize_value(val: Any) -> Any:
    """Convert non-serializable types to JSON-safe equivalents."""
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    return val


def _records_to_serializable(records: list[dict]) -> list[dict]:
    """Ensure all values in a list of dicts are JSON-serializable."""
    return [{k: _serialize_value(v) for k, v in rec.items()} for rec in records]


# ══════════════════════════════════════════════
# Metric 1: Daily event volume by type
# ══════════════════════════════════════════════


def daily_event_volume(
    start_date: date,
    end_date: date,
    session: Session | None = None,
) -> list[dict[str, Any]]:
    """Count telemetry events per day, broken down by event_type.

    Question answered:
        What is the daily volume pattern of telemetry events, and which
        event types dominate each day?

    SQL filtering:
        SELECT timestamp, event_type FROM telemetry_events
        WHERE timestamp >= start_date AND timestamp < end_date

    Pandas operations:
        pd.to_datetime(utc=True) -> .dt.date -> groupby(date, event_type)
        -> agg(count) -> sort_values -> to_dict(orient="records")

    Returns:
        list[dict] with keys: date, event_type, count
    """
    close_session = False
    if session is None:
        session = _get_session()
        close_session = True

    try:
        stmt = select(
            TelemetryEventTable.timestamp,
            TelemetryEventTable.event_type,
        ).where(
            TelemetryEventTable.timestamp >= _date_to_dt(start_date),
            TelemetryEventTable.timestamp < _date_to_dt(end_date),
        )
        rows = session.exec(stmt).all()
    finally:
        if close_session:
            session.close()

    if not rows:
        return []

    # Build DataFrame from rows
    df = pd.DataFrame(
        [
            {"timestamp": row.timestamp, "event_type": row.event_type}
            for row in rows
        ]
    )

    # Convert timestamp to UTC datetime
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # Extract date for daily grouping
    df["date"] = df["timestamp"].dt.date

    # Groupby + agg
    result = (
        df.groupby(["date", "event_type"])
        .agg(count=("event_type", "count"))
        .reset_index()
        .sort_values(["date", "event_type"])
    )

    return _records_to_serializable(result.to_dict(orient="records"))


# ══════════════════════════════════════════════
# Metric 2: Error breakdown by error_code
# ══════════════════════════════════════════════


def error_breakdown(
    start_date: date,
    end_date: date,
    session: Session | None = None,
) -> list[dict[str, Any]]:
    """Count api_server_error events grouped by error_code.

    Question answered:
        What server error codes are most frequent? This helps identify
        recurring system failures that need engineering attention.

    SQL filtering:
        SELECT tags FROM telemetry_events
        WHERE event_type = 'api_server_error'
        AND timestamp >= start_date AND timestamp < end_date

    Pandas operations:
        Extract error_code from tags -> dropna -> groupby(error_code)
        -> agg(count) -> compute pct -> sort_values

    Returns:
        list[dict] with keys: error_code, count, pct
    """
    close_session = False
    if session is None:
        session = _get_session()
        close_session = True

    try:
        stmt = select(TelemetryEventTable.tags).where(
            TelemetryEventTable.event_type == "api_server_error",
            TelemetryEventTable.timestamp >= _date_to_dt(start_date),
            TelemetryEventTable.timestamp < _date_to_dt(end_date),
        )
        rows = session.exec(stmt).all()
    finally:
        if close_session:
            session.close()

    if not rows:
        return []

    # When selecting a single column (tags), SQLModel returns the raw value directly
    df = pd.DataFrame(
        [{"tags": row} for row in rows]
    )

    # Extract error_code from tags
    df["error_code"] = df["tags"].apply(
        lambda t: _safe_tags(t).get("error_code")
    )

    # Drop rows where error_code is null
    df = df.dropna(subset=["error_code"])

    if df.empty:
        return []

    # Groupby + agg
    grouped = (
        df.groupby("error_code")
        .agg(count=("error_code", "count"))
        .reset_index()
        .sort_values("count", ascending=False)
    )

    # Add percentage column
    total = grouped["count"].sum()
    grouped["pct"] = (grouped["count"] / total * 100).round(2)

    return _records_to_serializable(grouped.to_dict(orient="records"))


# ══════════════════════════════════════════════
# Metric 3: Warehouse activity volume
# ══════════════════════════════════════════════


def warehouse_activity(
    start_date: date,
    end_date: date,
    session: Session | None = None,
) -> list[dict[str, Any]]:
    """Count inventory operations (inbound/outbound) grouped by warehouse.

    Question answered:
        What is the operational load per warehouse? This reveals whether
        one warehouse handles disproportionately more activity than another.

    SQL filtering:
        SELECT event_type, tags FROM telemetry_events
        WHERE event_type IN ('inbound_registered', 'outbound_registered')
        AND timestamp >= start_date AND timestamp < end_date

    Pandas operations:
        Extract warehouse from tags -> dropna -> groupby(warehouse, event_type)
        -> agg(count) -> sort_values

    Returns:
        list[dict] with keys: warehouse, event_type, count
    """
    close_session = False
    if session is None:
        session = _get_session()
        close_session = True

    try:
        stmt = select(
            TelemetryEventTable.event_type,
            TelemetryEventTable.tags,
        ).where(
            TelemetryEventTable.event_type.in_(
                ["inbound_registered", "outbound_registered"]
            ),
            TelemetryEventTable.timestamp >= _date_to_dt(start_date),
            TelemetryEventTable.timestamp < _date_to_dt(end_date),
        )
        rows = session.exec(stmt).all()
    finally:
        if close_session:
            session.close()

    if not rows:
        return []

    df = pd.DataFrame(
        [
            {"event_type": row.event_type, "tags": row.tags}
            for row in rows
        ]
    )

    # Extract warehouse from tags
    df["warehouse"] = df["tags"].apply(
        lambda t: _safe_tags(t).get("warehouse")
    )

    # Drop rows where warehouse is null
    df = df.dropna(subset=["warehouse"])

    if df.empty:
        return []

    # Groupby + agg
    result = (
        df.groupby(["warehouse", "event_type"])
        .agg(count=("event_type", "count"))
        .reset_index()
        .sort_values(["warehouse", "event_type"])
    )

    return _records_to_serializable(result.to_dict(orient="records"))


# ══════════════════════════════════════════════
# Metric 4: Page popularity
# ══════════════════════════════════════════════


def page_popularity(
    start_date: date,
    end_date: date,
    session: Session | None = None,
) -> list[dict[str, Any]]:
    """Count page_viewed events grouped by page identifier.

    Question answered:
        Which application pages are most frequently visited? This helps
        prioritize UX improvements and identify unused or broken pages.

    SQL filtering:
        SELECT tags FROM telemetry_events
        WHERE event_type = 'page_viewed'
        AND timestamp >= start_date AND timestamp < end_date

    Pandas operations:
        Extract page from tags -> dropna -> groupby(page) -> agg(count)
        -> sort_values(descending)

    Returns:
        list[dict] with keys: page, count
    """
    close_session = False
    if session is None:
        session = _get_session()
        close_session = True

    try:
        stmt = select(TelemetryEventTable.tags).where(
            TelemetryEventTable.event_type == "page_viewed",
            TelemetryEventTable.timestamp >= _date_to_dt(start_date),
            TelemetryEventTable.timestamp < _date_to_dt(end_date),
        )
        rows = session.exec(stmt).all()
    finally:
        if close_session:
            session.close()

    if not rows:
        return []

    # When selecting a single column (tags), SQLModel returns the raw value directly
    df = pd.DataFrame(
        [{"tags": row} for row in rows]
    )

    # Extract page from tags
    df["page"] = df["tags"].apply(
        lambda t: _safe_tags(t).get("page")
    )

    # Drop rows where page is null
    df = df.dropna(subset=["page"])

    if df.empty:
        return []

    # Groupby + agg
    result = (
        df.groupby("page")
        .agg(count=("page", "count"))
        .reset_index()
        .sort_values("count", ascending=False)
    )

    return _records_to_serializable(result.to_dict(orient="records"))