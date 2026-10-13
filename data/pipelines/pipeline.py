"""Resilient weekly warehouse/client performance pipeline.

Run from the repository root with ``python data/pipelines/pipeline.py``.
The four contractual event types and business formulas are fixed here; the
upstream source contract must provide the tag paths explicitly via environment
configuration before production use.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import threading
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

# This repository keeps the FastAPI application as a flat setuptools project.
# Resolve that project relative to this file for the required direct-script CLI;
# no developer-specific or machine-specific path is used.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_API_ROOT = _REPO_ROOT / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.reporting.models import PipelineRun, WeeklyWarehouseClientPerformance
from telemetry_models import TelemetryEventTable
from database import get_engine, init_db
from sqlmodel import Session
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select
from prefect.states import State
from prefect import flow, get_run_logger, task
from prefect.context import get_run_context


logger = logging.getLogger("business_performance_pipeline")
PIPELINE_NAME = "weekly_warehouse_client_performance_flow"
CONTRACT_EVENT_TYPES = (
    "inbound_order_created",
    "outbound_order_created",
    "stock_threshold_triggered",
    "inventory_discrepancy_detected",
)
CANONICAL_WAREHOUSES = frozenset({"los_angeles", "zaragoza"})
TRANSIENT_RETRIES = 3
RETRY_DELAY_SECONDS = 5
CACHE_EXPIRATION_SECONDS = 3600
_attempt_lock = threading.Lock()
_flow_retry_counts: dict[str, int] = {}
_prefect_flow_run_ids: dict[str, str] = {}


class ContractViolation(ValueError):
    """Deterministic source-contract error with safe counters only."""

    def __init__(self, reasons: dict[str, int], rejected: int):
        self.reasons = reasons
        self.rejected = rejected
        super().__init__("source_contract_violation")


def _retry_transient(_task, _task_run, state: State) -> bool:
    """Retry only connection/operational failures, never contract exceptions."""
    if not state.is_failed():
        return False
    try:
        error = state.result(raise_on_failure=False)
    except Exception:
        return False
    if not isinstance(error, DBAPIError):
        return False
    if error.connection_invalidated:
        return True
    original = getattr(error, "orig", None)
    code = str(getattr(original, "sqlstate", None) or getattr(original, "pgcode", ""))
    if code.startswith(("08", "40")):
        return True
    return isinstance(error, OperationalError) and "locked" in str(original).lower()


def _record_task_attempt(_task, task_run, _state: State) -> None:
    """Count real retries from Prefect TaskRun lifecycle metadata.

    Prefect invokes on_running for each attempt; run_count is 1 initially and
    increments on each retry. Only retries are persisted in PipelineRun.
    """
    try:
        attempt_number = int(task_run.run_count)
        prefect_flow_run_id = str(task_run.flow_run_id)
    except (AttributeError, TypeError, ValueError):
        return
    if attempt_number > 1:
        with _attempt_lock:
            run_id = _prefect_flow_run_ids.get(prefect_flow_run_id)
            if run_id is not None:
                _flow_retry_counts[run_id] = _flow_retry_counts.get(run_id, 0) + 1


def _retry_count_for_run(run_id: str, *, clear: bool = False) -> int:
    with _attempt_lock:
        if clear:
            return _flow_retry_counts.pop(run_id, 0)
        return _flow_retry_counts.get(run_id, 0)


def _bind_subflow_run(run_id: str | None) -> str | None:
    """Associate retry callbacks in a subflow with the parent PipelineRun."""
    if run_id is None:
        return None
    try:
        flow_run_id = str(get_run_context().flow_run.id)
    except (LookupError, AttributeError):
        return None
    with _attempt_lock:
        _prefect_flow_run_ids[flow_run_id] = run_id
    return flow_run_id


def _unbind_subflow_run(flow_run_id: str | None) -> None:
    if flow_run_id is not None:
        with _attempt_lock:
            _prefect_flow_run_ids.pop(flow_run_id, None)


def _cache_key(context, parameters: dict[str, Any]) -> str:
    """Cache only identical validated-transform inputs; never use a constant key."""
    payload = json.dumps(parameters, sort_keys=True,
                         default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _week_bounds(week_start: date) -> tuple[datetime, datetime]:
    if week_start.weekday() != 0:
        raise ValueError("week_start_must_be_monday")
    start = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=7)


def _configured_tag_paths() -> dict[str, str]:
    """Require explicit future source JSON paths; current layout is not presumed."""
    names = ("warehouse", "client_id")
    paths = {name: os.getenv(
        f"PIPELINE_TAG_PATH_{name.upper()}", "").strip() for name in names}
    missing = [name for name, path in paths.items() if not path]
    if missing:
        raise RuntimeError(
            "source_contract_paths_not_configured:" + ",".join(missing))
    paths["quantity"] = os.getenv("PIPELINE_TAG_PATH_QUANTITY", "").strip()
    return paths


def _read_tag_path(tags: Any, path: str) -> Any:
    value = tags
    for component in path.split("."):
        if not isinstance(value, dict) or component not in value:
            return None
        value = value[component]
    return value


def _serialize_event(event: TelemetryEventTable) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "timestamp": event.timestamp.isoformat(),
        "tags": event.tags if isinstance(event.tags, dict) else {},
    }


@task(
    name="extract_weekly_telemetry",
    retries=TRANSIENT_RETRIES,
    retry_delay_seconds=RETRY_DELAY_SECONDS,
    retry_condition_fn=_retry_transient,
    on_running=[_record_task_attempt],
)
def extract_weekly_telemetry(week_start: date) -> list[dict[str, Any]]:
    """Read only the four contract event types in the requested UTC week."""
    start, end = _week_bounds(week_start)
    statement = (
        select(TelemetryEventTable)
        .where(
            TelemetryEventTable.timestamp >= start,
            TelemetryEventTable.timestamp < end,
            TelemetryEventTable.event_type.in_(CONTRACT_EVENT_TYPES),
        )
        .order_by(TelemetryEventTable.timestamp, TelemetryEventTable.id)
    )
    with Session(get_engine()) as session:
        records = session.exec(statement).all()
        records = [row[0] if not isinstance(row, TelemetryEventTable) else row for row in records]
        return [_serialize_event(record) for record in records]


@task(name="validate_contractual_weekly_events")
def validate_contractual_weekly_events(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate the complete extracted batch before any KPI is calculated."""
    if not events:
        return []
    paths = _configured_tag_paths()
    reasons: dict[str, int] = {}
    normalized: list[dict[str, Any]] = []
    rejected_events = 0

    def reject(reason: str) -> None:
        reasons[reason] = reasons.get(reason, 0) + 1

    for event in events:
        event_type = event.get("event_type") if isinstance(event, dict) else None
        if event_type not in CONTRACT_EVENT_TYPES:
            reject("unsupported_event_type")
            rejected_events += 1
            continue
        tags = event.get("tags")
        warehouse = _read_tag_path(tags, paths["warehouse"])
        client_id = _read_tag_path(tags, paths["client_id"])
        invalid = False
        if not isinstance(warehouse, str) or warehouse not in CANONICAL_WAREHOUSES:
            reject("unknown_or_missing_warehouse")
            invalid = True
        if not isinstance(client_id, str) or not client_id.strip():
            reject("missing_or_invalid_client_id")
            invalid = True
        quantity: int | None = None
        if event_type == "inbound_order_created":
            if not paths["quantity"]:
                raise RuntimeError("source_contract_paths_not_configured:quantity")
            raw_quantity = _read_tag_path(tags, paths["quantity"])
            try:
                if isinstance(raw_quantity, bool):
                    raise InvalidOperation
                decimal_quantity = Decimal(str(raw_quantity))
                if (not decimal_quantity.is_finite() or decimal_quantity < 0
                        or decimal_quantity != decimal_quantity.to_integral_value()):
                    raise InvalidOperation
                quantity = int(decimal_quantity)
            except (InvalidOperation, TypeError, ValueError):
                reject("missing_or_invalid_quantity")
                invalid = True
        if invalid:
            rejected_events += 1
        else:
            normalized.append({
                "event_type": event_type,
                "warehouse": warehouse,
                "client_id": client_id,
                "quantity": quantity,
            })

    if reasons:
        raise ContractViolation(reasons, rejected_events)
    return normalized


@task(name="calculate_inbound_units_count")
def calculate_inbound_units_count(events: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    """Sum inbound quantities by warehouse and client."""
    totals: dict[tuple[str, str], int] = {}
    for event in events:
        if event["event_type"] == "inbound_order_created":
            key = (event["warehouse"], event["client_id"])
            totals[key] = totals.get(key, 0) + int(event["quantity"])
    return totals


@task(name="calculate_outbound_orders_count")
def calculate_outbound_orders_count(events: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    """Count outbound orders by warehouse and client."""
    totals: dict[tuple[str, str], int] = {}
    for event in events:
        if event["event_type"] == "outbound_order_created":
            key = (event["warehouse"], event["client_id"])
            totals[key] = totals.get(key, 0) + 1
    return totals


@task(name="calculate_stockout_events_count")
def calculate_stockout_events_count(events: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    """Count stock threshold events by warehouse and client."""
    totals: dict[tuple[str, str], int] = {}
    for event in events:
        if event["event_type"] == "stock_threshold_triggered":
            key = (event["warehouse"], event["client_id"])
            totals[key] = totals.get(key, 0) + 1
    return totals


@task(name="calculate_discrepancy_events_and_rate")
def calculate_discrepancy_events_and_rate(
    events: list[dict[str, Any]], outbound_orders: dict[tuple[str, str], int],
) -> dict[tuple[str, str], tuple[int, Decimal]]:
    """Count discrepancies and apply the contractual outbound denominator."""
    counts: dict[tuple[str, str], int] = {}
    for event in events:
        if event["event_type"] == "inventory_discrepancy_detected":
            key = (event["warehouse"], event["client_id"])
            counts[key] = counts.get(key, 0) + 1
    return {
        key: (count, Decimal(count) / Decimal(outbound_orders.get(key, 0))
              if outbound_orders.get(key, 0) else Decimal("0"))
        for key, count in counts.items()
    }


@task(name="compose_weekly_warehouse_client_performance")
def compose_weekly_warehouse_client_performance(
    week_start: date,
    events: list[dict[str, Any]],
    inbound: dict[tuple[str, str], int],
    outbound: dict[tuple[str, str], int],
    stockouts: dict[tuple[str, str], int],
    discrepancies: dict[tuple[str, str], tuple[int, Decimal]],
) -> list[dict[str, Any]]:
    """Compose KPI task results at warehouse + client + week grain."""
    keys = {(event["warehouse"], event["client_id"]) for event in events}
    rows = []
    for warehouse, client_id in sorted(keys):
        key = (warehouse, client_id)
        discrepancy_count, discrepancy_rate = discrepancies.get(
            key, (0, Decimal("0")))
        rows.append({
            "warehouse": warehouse,
            "client_id": client_id,
            "week_start": week_start,
            "inbound_units_count": inbound.get(key, 0),
            "outbound_orders_count": outbound.get(key, 0),
            "stockout_events_count": stockouts.get(key, 0),
            "discrepancy_events_count": discrepancy_count,
            "discrepancy_rate": discrepancy_rate,
        })
    return rows


@task(
    name="validate_and_aggregate_performance",
    cache_key_fn=_cache_key,
    cache_expiration=timedelta(seconds=CACHE_EXPIRATION_SECONDS),
)
def validate_and_aggregate_performance(
    week_start: date, events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Validate the entire batch, then calculate independent domain KPIs."""
    normalized = validate_contractual_weekly_events(events)
    inbound = calculate_inbound_units_count(normalized)
    outbound = calculate_outbound_orders_count(normalized)
    stockouts = calculate_stockout_events_count(normalized)
    discrepancies = calculate_discrepancy_events_and_rate(normalized, outbound)
    return compose_weekly_warehouse_client_performance(
        week_start, normalized, inbound, outbound, stockouts, discrepancies)


@task(
    name="upsert_weekly_performance",
    retries=2,
    retry_delay_seconds=RETRY_DELAY_SECONDS,
    retry_condition_fn=_retry_transient,
    on_running=[_record_task_attempt],
)
def upsert_weekly_performance(aggregates: list[dict[str, Any]]) -> int:
    """Atomically UPSERT all groups by natural key; source table is never touched."""
    if not aggregates:
        return 0
    engine = get_engine()
    dialect = engine.dialect.name
    table = WeeklyWarehouseClientPerformance.__table__
    insert_factory = pg_insert if dialect == "postgresql" else sqlite_insert
    rows = [
        {key: value for key, value in row.items() if key != "computed_at"}
        for row in aggregates
    ]
    with Session(engine) as session:
        try:
            statement = insert_factory(table).values(rows)
            statement = statement.on_conflict_do_update(
                index_elements=[table.c.warehouse,
                                table.c.client_id, table.c.week_start],
                set_={
                    "inbound_units_count": statement.excluded.inbound_units_count,
                    "outbound_orders_count": statement.excluded.outbound_orders_count,
                    "stockout_events_count": statement.excluded.stockout_events_count,
                    "discrepancy_events_count": statement.excluded.discrepancy_events_count,
                    "discrepancy_rate": statement.excluded.discrepancy_rate,
                    "computed_at": datetime.now(timezone.utc),
                },
            )
            session.exec(statement)
            session.commit()
        except Exception:
            session.rollback()
            raise
    return len(rows)


@task(name="log_operational_summary")
def log_operational_summary(summary: dict[str, Any]) -> None:
    """Best-effort, non-critical operational summary logging."""
    if os.getenv("PIPELINE_OPTIONAL_SUMMARY_FAIL") == "1":
        raise RuntimeError("optional_summary_unavailable")
    get_run_logger().info("Weekly pipeline summary: %s", summary)


@flow(name="extract_weekly_warehouse_client_telemetry_flow")
def extract_weekly_warehouse_client_telemetry_flow(
    week_start: date, pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Extract contractual telemetry for one week, independently reusable."""
    flow_run_id = _bind_subflow_run(pipeline_run_id)
    try:
        state = extract_weekly_telemetry(week_start, return_state=True)
        if state.is_failed():
            error = state.result(raise_on_failure=False)
            raise error if isinstance(error, BaseException) else RuntimeError("extraction_failed")
        return state.result()
    finally:
        _unbind_subflow_run(flow_run_id)


@flow(name="transform_weekly_warehouse_client_performance_flow")
def transform_weekly_warehouse_client_performance_flow(
    week_start: date, events: list[dict[str, Any]],
    pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Validate and calculate the reporting grain for an explicit event batch."""
    flow_run_id = _bind_subflow_run(pipeline_run_id)
    try:
        state = validate_and_aggregate_performance(
            week_start, events, return_state=True)
        if state.is_failed():
            error = state.result(raise_on_failure=False)
            raise error if isinstance(error, BaseException) else RuntimeError("transformation_failed")
        return state.result()
    finally:
        _unbind_subflow_run(flow_run_id)


@flow(name="load_weekly_warehouse_client_performance_flow")
def load_weekly_warehouse_client_performance_flow(
    aggregates: list[dict[str, Any]], pipeline_run_id: str | None = None,
) -> int:
    """Atomically upsert an explicit set of weekly reporting aggregates."""
    flow_run_id = _bind_subflow_run(pipeline_run_id)
    try:
        state = upsert_weekly_performance(aggregates, return_state=True)
        if state.is_failed():
            error = state.result(raise_on_failure=False)
            raise error if isinstance(error, BaseException) else RuntimeError("load_failed")
        return int(state.result())
    finally:
        _unbind_subflow_run(flow_run_id)


@flow(name="log_weekly_performance_summary_flow")
def log_weekly_performance_summary_flow(
    summary: dict[str, Any], pipeline_run_id: str | None = None,
) -> None:
    """Run optional, non-critical operational summary logging."""
    flow_run_id = _bind_subflow_run(pipeline_run_id)
    try:
        state = log_operational_summary(summary, return_state=True)
        if state.is_failed():
            error = state.result(raise_on_failure=False)
            raise error if isinstance(error, BaseException) else RuntimeError("summary_logging_failed")
    finally:
        _unbind_subflow_run(flow_run_id)


def _safe_error_summary(error: BaseException) -> str:
    if isinstance(error, ContractViolation):
        return "source_contract_violation"
    if isinstance(error, RuntimeError) and str(error).startswith("source_contract_paths_not_configured"):
        return "source_contract_paths_not_configured"
    return f"pipeline_failure:{type(error).__name__}"


def _insert_run(week_start: date) -> str:
    run = PipelineRun(pipeline_name=PIPELINE_NAME, week_start=week_start)
    with Session(get_engine()) as session:
        session.add(run)
        session.commit()
        session.refresh(run)
        return run.id


def _complete_run(
    run_id: str,
    *,
    state: str,
    events_read: int,
    events_rejected: int = 0,
    reasons: dict[str, int] | None = None,
    groups: int = 0,
    rows: int = 0,
    retry_count: int = 0,
    error_summary: str | None = None,
) -> None:
    with Session(get_engine()) as session:
        run = session.get(PipelineRun, run_id)
        if run is None:
            return
        run.state = state
        run.completed_at = datetime.now(timezone.utc)
        run.events_read = events_read
        run.events_rejected = events_rejected
        run.events_rejected_reasons = reasons or {}
        run.groups_aggregated = groups
        run.rows_upserted = rows
        run.retry_count = retry_count
        run.error_summary = error_summary
        session.add(run)
        session.commit()


@flow(name=PIPELINE_NAME, log_prints=True)
def weekly_warehouse_client_performance_flow(week_start: date) -> dict[str, Any]:
    """Extract -> validate/aggregate -> load, then persist terminal run metadata."""
    _week_bounds(week_start)
    run_id = _insert_run(week_start)
    try:
        prefect_flow_run_id = str(get_run_context().flow_run.id)
    except (LookupError, AttributeError):
        prefect_flow_run_id = ""
    with _attempt_lock:
        _flow_retry_counts[run_id] = 0
        if prefect_flow_run_id:
            _prefect_flow_run_ids[prefect_flow_run_id] = run_id
    events_read = 0
    groups = 0
    rows = 0
    retry_count = 0
    try:
        extraction_state = extract_weekly_warehouse_client_telemetry_flow(
            week_start, pipeline_run_id=run_id, return_state=True)
        if extraction_state.is_failed():
            error = extraction_state.result(raise_on_failure=False)
            raise error if isinstance(error, BaseException) else RuntimeError("extraction_failed")
        events = extraction_state.result()
        events_read = len(events)

        transform_state = transform_weekly_warehouse_client_performance_flow(
            week_start, events, pipeline_run_id=run_id, return_state=True)
        if transform_state.is_failed():
            error = transform_state.result(raise_on_failure=False)
            raise error if isinstance(error, BaseException) else RuntimeError("transformation_failed")
        aggregates = transform_state.result()
        groups = len(aggregates)

        load_state = load_weekly_warehouse_client_performance_flow(
            aggregates, pipeline_run_id=run_id, return_state=True)
        if load_state.is_failed():
            error = load_state.result(raise_on_failure=False)
            raise error if isinstance(error, BaseException) else RuntimeError("load_failed")
        rows = int(load_state.result())

        optional_state = log_weekly_performance_summary_flow(
            {"run_id": run_id, "events_read": events_read,
                "groups": groups, "rows": rows},
            pipeline_run_id=run_id,
            return_state=True,
        )
        if optional_state.is_failed():
            get_run_logger().warning(
                "Optional operational summary task failed; main run remains successful")

        with _attempt_lock:
            if prefect_flow_run_id:
                _prefect_flow_run_ids.pop(prefect_flow_run_id, None)
        _complete_run(
            run_id,
            state="Completed",
            events_read=events_read,
            groups=groups,
            rows=rows,
            retry_count=_retry_count_for_run(run_id, clear=True),
        )
        return {"run_id": run_id, "state": "Completed", "events_read": events_read, "groups_aggregated": groups, "rows_upserted": rows}
    except Exception as error:
        if prefect_flow_run_id:
            with _attempt_lock:
                _prefect_flow_run_ids.pop(prefect_flow_run_id, None)
        retry_count = _retry_count_for_run(run_id, clear=True)
        reasons = error.reasons if isinstance(error, ContractViolation) else {}
        _complete_run(
            run_id,
            state="Failed",
            events_read=events_read,
            events_rejected=error.rejected if isinstance(error, ContractViolation) else 0,
            reasons=reasons,
            retry_count=retry_count,
            groups=0,
            rows=0,
            error_summary=_safe_error_summary(error),
        )
        raise


def most_recent_completed_week(today: date | None = None) -> date:
    """Return Monday of the most recently completed ISO week (UTC calendar)."""
    current = today or datetime.now(timezone.utc).date()
    this_monday = current - timedelta(days=current.weekday())
    return this_monday - timedelta(days=7)


def main() -> int:
    """CLI entry point; the DB must be explicitly configured for local SQLite."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week-start", type=date.fromisoformat,
                        help="Monday ISO date; default is the most recent completed week")
    args = parser.parse_args()
    week_start = args.week_start or most_recent_completed_week()
    init_db()
    state = weekly_warehouse_client_performance_flow(
        week_start, return_state=True
    )
    if state.is_failed():
        error = state.result(raise_on_failure=False)
        print(
            f"Pipeline failed: {_safe_error_summary(error)}", file=sys.stderr)
        return 1
    print(json.dumps(state.result(), default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
