"""Shared telemetry report date handling and metric computation."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from collections.abc import Callable
from typing import Any

from sqlmodel import Session

from telemetry.analysis import (
    _date_to_dt,
    daily_event_volume,
    error_breakdown,
    page_popularity,
    warehouse_activity,
)


def resolve_report_window(
    start_date: str | None,
    end_date: str | None,
    *,
    now: datetime | None = None,
) -> tuple[date, date, datetime, datetime]:
    """Parse report dates and return cache dates and exclusive UTC bounds."""
    current = now or datetime.now(timezone.utc)
    current = current if current.tzinfo else current.replace(
        tzinfo=timezone.utc)

    if end_date is not None:
        end = date.fromisoformat(end_date)
        end_bound = _date_to_dt(end)
    else:
        end = current.date()
        end_bound = current

    if start_date is not None:
        start = date.fromisoformat(start_date)
        start_bound = _date_to_dt(start)
    else:
        start = end - timedelta(days=7)
        start_bound = current - timedelta(days=7)

    if start_bound >= end_bound:
        raise ValueError("start_date must be earlier than end_date")

    return start, end, start_bound, end_bound


def build_telemetry_report(
    session: Session,
    start_bound: datetime,
    end_bound: datetime,
    start: date,
    end: date,
    *,
    metric_functions: dict[str, Callable[...,
                                         list[dict[str, Any]]]] | None = None,
) -> dict[str, Any]:
    """Compute all four report metric groups using the supplied session."""
    functions = metric_functions or {
        "events_per_day": daily_event_volume,
        "error_rate_by_type": error_breakdown,
        "warehouse_activity": warehouse_activity,
        "page_popularity": page_popularity,
    }
    return {
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "metrics": {
            name: function(start_bound, end_bound, session)
            for name, function in functions.items()
        },
    }
