from __future__ import annotations
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

# This test can be invoked by file path from the repository root, in which
# case pytest does not necessarily add the repository root to sys.path. Add
# both package roots before importing application and pipeline modules.
ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "services" / "api"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if str(API_ROOT) not in sys.path:
    sys.path.insert(1, str(API_ROOT))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import database
import main
import security
from data.pipelines import pipeline
from services.reporting.models import (
    PipelineRun,
    ReportingBase,
    WeeklyWarehouseClientPerformance,
    create_reporting_tables,
)
from telemetry_models import TelemetryEventTable

@pytest.fixture
def reporting_engine(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": {"reporting": None}},
    )
    SQLModel.metadata.create_all(engine)
    create_reporting_tables(engine)
    monkeypatch.setattr(database, "get_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(pipeline, "get_engine", lambda: engine)
    yield engine
    engine.dispose()


@pytest.fixture
def reporting_client(reporting_engine):
    from database import get_db

    def override_db():
        with Session(reporting_engine) as session:
            yield session

    main.app.dependency_overrides[get_db] = override_db
    with TestClient(main.app) as client:
        yield client
    main.app.dependency_overrides.clear()


@pytest.fixture
def auth_client(reporting_engine):
    from database import get_db

    def override_db():
        with Session(reporting_engine) as session:
            yield session

    main.app.dependency_overrides[get_db] = override_db
    main.app.dependency_overrides[security.get_current_user] = lambda: {
        "id": 1, "email": "test@example.com"}
    with TestClient(main.app) as client:
        yield client
    main.app.dependency_overrides.clear()


def event(event_type: str, tags: dict, timestamp: datetime | None = None):
    return TelemetryEventTable(
        timestamp=timestamp or datetime(2025, 1, 6, 12, tzinfo=timezone.utc),
        service="test",
        event_type=event_type,
        level="info",
        value=None,
        message=None,
        tags=tags,
    )


def configure_paths(monkeypatch):
    monkeypatch.setenv("PIPELINE_TAG_PATH_WAREHOUSE", "warehouse")
    monkeypatch.setenv("PIPELINE_TAG_PATH_CLIENT_ID", "client_id")
    monkeypatch.setenv("PIPELINE_TAG_PATH_QUANTITY", "quantity")


def test_aggregate_exact_four_metrics_and_rate(monkeypatch):
    configure_paths(monkeypatch)
    events = [
        {"event_type": "inbound_order_created", "tags": {
            "warehouse": "los_angeles", "client_id": "c-1", "quantity": 12}},
        {"event_type": "outbound_order_created", "tags": {
            "warehouse": "los_angeles", "client_id": "c-1"}},
        {"event_type": "outbound_order_created", "tags": {
            "warehouse": "los_angeles", "client_id": "c-1"}},
        {"event_type": "stock_threshold_triggered", "tags": {
            "warehouse": "los_angeles", "client_id": "c-1"}},
        {"event_type": "inventory_discrepancy_detected", "tags": {
            "warehouse": "los_angeles", "client_id": "c-1"}},
    ]
    result = pipeline.validate_and_aggregate_performance.fn(
        date(2025, 1, 6), events)
    assert len(result) == 1
    assert {k: result[0][k] for k in ("inbound_units_count", "outbound_orders_count", "stockout_events_count", "discrepancy_events_count")} == {
        "inbound_units_count": 12,
        "outbound_orders_count": 2,
        "stockout_events_count": 1,
        "discrepancy_events_count": 1,
    }
    assert result[0]["discrepancy_rate"] == Decimal("0.5")


def test_transform_cache_is_parameter_keyed_and_expires():
    task = pipeline.validate_and_aggregate_performance
    first = {"week_start": date(2025, 1, 6),
             "events": [{"event_type": "outbound_order_created"}]}
    changed = {"week_start": date(2025, 1, 6),
               "events": [{"event_type": "stock_threshold_triggered"}]}

    assert task.cache_key_fn is pipeline._cache_key
    assert task.cache_expiration.total_seconds() == pipeline.CACHE_EXPIRATION_SECONDS
    assert pipeline._cache_key(None, first) == pipeline._cache_key(None, first)
    assert pipeline._cache_key(
        None, first) != pipeline._cache_key(None, changed)


def test_multiple_clients_produce_separate_groups_and_rows(reporting_engine, monkeypatch):
    configure_paths(monkeypatch)
    events = [
        {"event_type": "inbound_order_created", "tags": {
            "warehouse": "zaragoza", "client_id": client, "quantity": quantity}}
        for client, quantity in (("client-a", 3), ("client-b", 8))
    ]
    groups = pipeline.validate_and_aggregate_performance.fn(
        date(2025, 1, 6), events)

    assert {(row["warehouse"], row["client_id"], row["inbound_units_count"])
            for row in groups} == {
                ("zaragoza", "client-a", 3), ("zaragoza", "client-b", 8)}
    assert pipeline.upsert_weekly_performance.fn(groups) == 2
    assert {(row.warehouse, row.client_id, row.inbound_units_count)
            for row in _stored_rows(reporting_engine)} == {
                ("zaragoza", "client-a", 3), ("zaragoza", "client-b", 8)}


def test_empty_week_succeeds_without_source_paths():
    assert pipeline.validate_and_aggregate_performance.fn(
        date(2025, 1, 6), []) == []


@pytest.mark.parametrize("warehouse", ["LA", "ZGZ", "unknown", ""])
def test_rejects_noncanonical_warehouse(warehouse, monkeypatch):
    configure_paths(monkeypatch)
    data = [{"event_type": "outbound_order_created",
             "tags": {"warehouse": warehouse, "client_id": "c"}}]
    with pytest.raises(pipeline.ContractViolation):
        pipeline.validate_and_aggregate_performance.fn(date(2025, 1, 6), data)


def test_rejects_missing_client_and_invalid_quantity(monkeypatch):
    configure_paths(monkeypatch)
    bad = [
        {"event_type": "inbound_order_created", "tags": {
            "warehouse": "zaragoza", "client_id": "c-1", "quantity": -1}},
        {"event_type": "outbound_order_created", "tags": {
            "warehouse": "zaragoza", "client_id": " "}},
    ]
    with pytest.raises(pipeline.ContractViolation) as exc:
        pipeline.validate_and_aggregate_performance.fn(date(2025, 1, 6), bad)
    assert exc.value.rejected == 2
    assert exc.value.reasons["missing_or_invalid_quantity"] == 1
    assert exc.value.reasons["missing_or_invalid_client_id"] == 1


def test_empty_outbound_denominator_is_zero(monkeypatch):
    configure_paths(monkeypatch)
    events = [{"event_type": "inventory_discrepancy_detected",
               "tags": {"warehouse": "zaragoza", "client_id": "c"}}]
    result = pipeline.validate_and_aggregate_performance.fn(
        date(2025, 1, 6), events)
    assert result[0]["discrepancy_rate"] == Decimal("0")


def test_extract_filters_event_types_and_utc_week(reporting_engine):
    with Session(reporting_engine) as session:
        session.add_all([
            event("outbound_order_created", {}, datetime(
                2025, 1, 6, tzinfo=timezone.utc)),
            event("sku_created", {}, datetime(
                2025, 1, 6, tzinfo=timezone.utc)),
            event("stock_threshold_triggered", {}, datetime(
                2025, 1, 13, tzinfo=timezone.utc)),
        ])
        session.commit()
    result = pipeline.extract_weekly_telemetry.fn(date(2025, 1, 6))
    assert [item["event_type"]
            for item in result] == ["outbound_order_created"]


def test_upsert_is_idempotent_and_updates_computed_at(reporting_engine):
    row = {"warehouse": "zaragoza", "client_id": "c", "week_start": date(
        2025, 1, 6), "inbound_units_count": 7, "outbound_orders_count": 1, "stockout_events_count": 0, "discrepancy_events_count": 0, "discrepancy_rate": Decimal("0")}
    assert pipeline.upsert_weekly_performance.fn([row]) == 1
    first = datetime.now(timezone.utc)
    row["inbound_units_count"] = 9
    assert pipeline.upsert_weekly_performance.fn([row]) == 1
    with Session(reporting_engine) as session:
        stored = session.exec(select(WeeklyWarehouseClientPerformance)).all()
    assert len(stored) == 1
    assert stored[0].inbound_units_count == 9
    assert stored[0].computed_at.replace(tzinfo=timezone.utc) >= first


def test_flow_persists_completed_run_for_empty_week(reporting_engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setattr(pipeline, "get_engine", lambda: reporting_engine)
    state = pipeline.weekly_warehouse_client_performance_flow(
        date(2025, 1, 6), return_state=True
    )
    assert state.is_completed()
    result = state.result()
    with Session(reporting_engine) as session:
        run = session.get(PipelineRun, result["run_id"])
    assert run is not None
    assert run.state == "Completed"
    assert run.events_read == 0
    assert run.events_rejected == 0
    assert run.groups_aggregated == 0
    assert run.rows_upserted == 0
    assert run.retry_count == 0


@pytest.mark.parametrize(
    ("event_type", "tags", "reason"),
    [
        ("outbound_order_created", {"warehouse": "zaragoza"},
         "missing_or_invalid_client_id"),
        ("inbound_order_created", {"warehouse": "zaragoza", "client_id": "c-1"},
         "missing_or_invalid_quantity"),
    ],
)
def test_invalid_source_contract_fails_full_flow_without_load_or_retry(
    reporting_engine, monkeypatch, event_type, tags, reason
):
    configure_paths(monkeypatch)
    with Session(reporting_engine) as session:
        session.add(event(event_type, tags))
        session.commit()

    load_calls = []
    original_load = pipeline.upsert_weekly_performance.fn

    def unexpected_load(rows):
        load_calls.append(rows)
        return original_load(rows)

    monkeypatch.setattr(pipeline.upsert_weekly_performance,
                        "fn", unexpected_load)
    state = pipeline.weekly_warehouse_client_performance_flow(
        date(2025, 1, 6), return_state=True)

    assert state.is_failed()
    assert load_calls == []
    assert _stored_rows(reporting_engine) == []
    error = state.result(raise_on_failure=False)
    assert isinstance(error, pipeline.ContractViolation)
    assert error.rejected == 1
    assert error.reasons[reason] == 1
    with Session(reporting_engine) as session:
        run = session.exec(select(PipelineRun)).one()
    assert run.state == "Failed"
    assert run.events_read == 1
    assert run.events_rejected == 1
    assert run.groups_aggregated == 0
    assert run.rows_upserted == 0
    assert run.retry_count == 0
    assert run.events_rejected_reasons[reason] == 1


def test_reporting_routes_require_auth(reporting_client):
    # Router dependency is authenticated; no credentials are rejected.
    response = reporting_client.get(
        "/reporting/weekly-warehouse-client-performance")
    assert response.status_code == 401
    weekly = reporting_client.get(
        "/reporting/weekly-warehouse-client-performance")
    assert weekly.status_code == 401
    latest = reporting_client.get("/reporting/pipeline-runs/latest")
    assert latest.status_code == 401
    manual = reporting_client.post("/reporting/pipeline-runs", json={})
    assert manual.status_code == 401


def test_authenticated_reporting_route_and_latest_run(auth_client, reporting_engine):
    first = PipelineRun(pipeline_name=pipeline.PIPELINE_NAME,
                        week_start=date(2025, 1, 6), state="Completed",
                        started_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    latest = PipelineRun(pipeline_name=pipeline.PIPELINE_NAME,
                         week_start=date(2025, 1, 13), state="Failed",
                         started_at=datetime(2025, 1, 2, tzinfo=timezone.utc))
    with Session(reporting_engine) as session:
        session.add_all([first, latest])
        session.commit()
        latest_id = latest.id
    response = auth_client.get("/reporting/pipeline-runs/latest")
    assert response.status_code == 200
    assert response.json()["id"] == latest_id
    assert response.json()["state"] == "Failed"


def test_most_recent_completed_week():
    assert pipeline.most_recent_completed_week(
        date(2025, 1, 8)) == date(2024, 12, 30)
    assert pipeline.most_recent_completed_week(
        date(2025, 1, 13)) == date(2025, 1, 6)


def _stored_rows(engine):
    with Session(engine) as session:
        return session.exec(select(WeeklyWarehouseClientPerformance)).all()


def test_invalid_contract_fails_flow_without_load_or_retry(
    reporting_engine, monkeypatch
):
    configure_paths(monkeypatch)
    with Session(reporting_engine) as session:
        session.add(event("outbound_order_created", {
            "warehouse": "LA", "client_id": "client-1"}))
        session.commit()

    load_calls = []
    load_task = pipeline.upsert_weekly_performance
    original_fn = load_task.fn

    def unexpected_load(aggregates):
        load_calls.append(aggregates)
        return original_fn(aggregates)

    monkeypatch.setattr(load_task, "fn", unexpected_load)
    state = pipeline.weekly_warehouse_client_performance_flow(
        date(2025, 1, 6), return_state=True)

    assert state.is_failed()
    assert load_calls == []
    assert _stored_rows(reporting_engine) == []
    result = state.result(raise_on_failure=False)
    assert isinstance(result, pipeline.ContractViolation)
    with Session(reporting_engine) as session:
        run = session.exec(select(PipelineRun)).one()
    assert run.state == "Failed"
    assert run.events_rejected == 1
    assert run.retry_count == 0


def test_upsert_failure_rolls_back_existing_and_new_rows(reporting_engine):
    existing = {
        "warehouse": "zaragoza", "client_id": "existing",
        "week_start": date(2025, 1, 6), "inbound_units_count": 3,
        "outbound_orders_count": 1, "stockout_events_count": 0,
        "discrepancy_events_count": 0, "discrepancy_rate": Decimal("0"),
    }
    pipeline.upsert_weekly_performance.fn([existing])
    before = _stored_rows(reporting_engine)[0]
    existing["inbound_units_count"] = 99
    new_row = {**existing, "client_id": "new", "inbound_units_count": 7}
    raised = False

    def fail_after_statement(conn, cursor, statement, parameters, context, executemany):
        nonlocal raised
        if not raised and "INSERT INTO" in statement.upper():
            raised = True
            raise RuntimeError("controlled post-execution failure")

    sqlalchemy_event.listen(
        reporting_engine, "after_cursor_execute", fail_after_statement)
    try:
        with pytest.raises(RuntimeError, match="controlled post-execution failure"):
            pipeline.upsert_weekly_performance.fn([existing, new_row])
    finally:
        sqlalchemy_event.remove(
            reporting_engine, "after_cursor_execute", fail_after_statement)

    assert raised
    rows = _stored_rows(reporting_engine)
    assert len(rows) == 1
    assert rows[0].client_id == "existing"
    assert rows[0].inbound_units_count == before.inbound_units_count


def test_transient_load_retry_persists_real_attempt_count(reporting_engine, monkeypatch):
    monkeypatch.setenv("PIPELINE_TAG_PATH_WAREHOUSE", "warehouse")
    monkeypatch.setenv("PIPELINE_TAG_PATH_CLIENT_ID", "client_id")
    monkeypatch.setenv("PIPELINE_TAG_PATH_QUANTITY", "quantity")
    with Session(reporting_engine) as session:
        session.add(event("inbound_order_created", {
            "warehouse": "zaragoza", "client_id": "retry-client", "quantity": 4}))
        session.commit()

    task = pipeline.upsert_weekly_performance.with_options(
        retries=2, retry_delay_seconds=0)
    real_load = task.fn
    attempts = 0

    def fail_once_then_load(aggregates):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OperationalError(
                "insert", {}, Exception("database is locked"))
        return real_load(aggregates)

    task.fn = fail_once_then_load
    monkeypatch.setattr(pipeline, "upsert_weekly_performance", task)
    state = pipeline.weekly_warehouse_client_performance_flow(
        date(2025, 1, 6), return_state=True)
    assert state.is_completed()
    assert attempts == 2
    with Session(reporting_engine) as session:
        run = session.get(PipelineRun, state.result()["run_id"])
    assert run.state == "Completed"
    assert run.retry_count == 1


def test_failed_run_persists_retry_count_for_failed_transient_load(
    reporting_engine, monkeypatch
):
    monkeypatch.setenv("PIPELINE_TAG_PATH_WAREHOUSE", "warehouse")
    monkeypatch.setenv("PIPELINE_TAG_PATH_CLIENT_ID", "client_id")
    monkeypatch.setenv("PIPELINE_TAG_PATH_QUANTITY", "quantity")
    with Session(reporting_engine) as session:
        session.add(event("inbound_order_created", {
            "warehouse": "zaragoza", "client_id": "retry-client", "quantity": 4}))
        session.commit()

    task = pipeline.upsert_weekly_performance.with_options(
        retries=1, retry_delay_seconds=0)
    attempts = 0

    def always_transient_failure(_aggregates):
        nonlocal attempts
        attempts += 1
        raise OperationalError("insert", {}, Exception("database is locked"))

    task.fn = always_transient_failure
    monkeypatch.setattr(pipeline, "upsert_weekly_performance", task)
    state = pipeline.weekly_warehouse_client_performance_flow(
        date(2025, 1, 6), return_state=True)
    assert state.is_failed()
    assert attempts == 2
    with Session(reporting_engine) as session:
        run = session.exec(select(PipelineRun)).one()
    assert run.state == "Failed"
    assert run.retry_count == 1


def test_contract_violation_is_not_retryable():
    from prefect.states import Failed

    state = Failed(data=pipeline.ContractViolation({"bad": 1}, 1))
    assert pipeline._retry_transient(None, None, state) is False


def test_optional_task_failure_state_is_failed_but_noncritical(
    reporting_engine, monkeypatch
):
    monkeypatch.setenv("PIPELINE_OPTIONAL_SUMMARY_FAIL", "1")
    original_task = pipeline.log_operational_summary
    optional_states = []

    def capture_optional_state(summary, return_state=False):
        task_state = original_task(summary, return_state=True)
        optional_states.append(task_state)
        return task_state

    monkeypatch.setattr(pipeline, "log_operational_summary",
                        capture_optional_state)
    state = pipeline.weekly_warehouse_client_performance_flow(
        date(2025, 1, 6), return_state=True)
    assert state.is_completed()
    assert len(optional_states) == 1
    assert optional_states[0].is_failed()
    with Session(reporting_engine) as session:
        run = session.get(PipelineRun, state.result()["run_id"])
    assert run.state == "Completed"


def test_reporting_weekly_endpoint_explicit_and_default_week(auth_client, reporting_engine):
    rows = [
        WeeklyWarehouseClientPerformance(
            warehouse=warehouse, client_id=client, week_start=week,
            inbound_units_count=1, outbound_orders_count=0,
            stockout_events_count=0, discrepancy_events_count=0,
            discrepancy_rate=Decimal("0"),
        )
        for week, warehouse, client in (
            (date(2025, 1, 6), "zaragoza", "c-1"),
            (date(2025, 1, 6), "los_angeles", "c-2"),
            (date(2025, 1, 13), "zaragoza", "c-3"),
        )
    ]
    with Session(reporting_engine) as session:
        session.add_all(rows)
        session.commit()

    explicit = auth_client.get(
        "/reporting/weekly-warehouse-client-performance",
        params={"week_start": "2025-01-06"})
    assert explicit.status_code == 200
    assert {(r["warehouse"], r["client_id"]) for r in explicit.json()} == {
        ("zaragoza", "c-1"), ("los_angeles", "c-2")}
    latest = auth_client.get("/reporting/weekly-warehouse-client-performance")
    assert latest.status_code == 200
    assert [(r["warehouse"], r["client_id"]) for r in latest.json()] == [
        ("zaragoza", "c-3")]


def test_manual_run_endpoint_auth_success_and_invalid_week(
    auth_client, reporting_engine
):
    invalid = auth_client.post(
        "/reporting/pipeline-runs", json={"week_start": "2025-01-07"})
    assert invalid.status_code == 422

    response = auth_client.post(
        "/reporting/pipeline-runs", json={"week_start": "2025-01-06"})
    assert response.status_code == 202
    payload = response.json()
    assert payload["state"] == "Completed"
    assert payload["run_id"]
    with Session(reporting_engine) as session:
        run = session.get(PipelineRun, payload["run_id"])
    assert run is not None and run.state == "Completed"


def test_manual_run_without_week_uses_default_and_canonical_flow(
    auth_client, reporting_engine, monkeypatch
):
    expected_week = date(2025, 1, 6)
    monkeypatch.setattr(pipeline, "most_recent_completed_week",
                        lambda today=None: expected_week)
    original_flow = pipeline.weekly_warehouse_client_performance_flow
    called = []

    def observe_flow(week_start, **kwargs):
        called.append(week_start)
        return original_flow(week_start, **kwargs)

    monkeypatch.setattr(pipeline, "weekly_warehouse_client_performance_flow",
                        observe_flow)
    response = auth_client.post("/reporting/pipeline-runs", json={})

    assert response.status_code == 202
    assert called == [expected_week]
    with Session(reporting_engine) as session:
        run = session.get(PipelineRun, response.json()["run_id"])
    assert run is not None and run.week_start == expected_week


def test_repository_root_cli_runs_without_pythonpath(tmp_path):
    database_path = tmp_path / "pipeline-cli.sqlite"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    command = [
        "uv", "run", "--project", str(ROOT / "services" / "api"),
        "--no-sync", "python", str(ROOT / "data" /
                                   "pipelines" / "pipeline.py"),
    ]
    result = subprocess.run(
        command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Completed" in result.stdout + result.stderr
    assert database_path.exists()


def test_manual_run_endpoint_returns_safe_conflict_on_contract_failure(
    auth_client, reporting_engine, monkeypatch
):
    configure_paths(monkeypatch)
    with Session(reporting_engine) as session:
        session.add(event("outbound_order_created", {
            "warehouse": "LA", "client_id": "client-1"}))
        session.commit()

    response = auth_client.post(
        "/reporting/pipeline-runs", json={"week_start": "2025-01-06"})
    assert response.status_code == 409
    assert response.json()["detail"] == "source_contract_violation"
    with Session(reporting_engine) as session:
        run = session.exec(select(PipelineRun)).one()
    assert run.state == "Failed"
    assert run.retry_count == 0
    assert "LA" not in (run.error_summary or "")


def test_reporting_metadata_isolated_and_legacy_create_all_safe(reporting_engine):
    assert WeeklyWarehouseClientPerformance.metadata is ReportingBase.metadata
    assert WeeklyWarehouseClientPerformance.metadata is not SQLModel.metadata
    assert WeeklyWarehouseClientPerformance.__table__.schema == "reporting"
    SQLModel.metadata.create_all(reporting_engine)
    create_reporting_tables(reporting_engine)
    names = set(reporting_engine.connect().exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type='table'").scalars())
    assert "weekly_warehouse_client_performance" in names
    assert "pipeline_runs" in names
