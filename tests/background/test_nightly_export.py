from telemetry_models import TelemetryEventTable
from services.job_runner import (
    acquire_processing_lock,
    create_or_get_job,
    has_completed_for_date,
    has_processing_lock,
    mark_completed,
    mark_failed,
)
from services.job_models import JobRun
from datetime import date, datetime, timedelta, timezone
import csv
import importlib.util
import multiprocessing
from pathlib import Path
import sys

import pytest

from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine, select

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "services" / "api"
for path in (ROOT, API_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


SPEC = importlib.util.spec_from_file_location(
    "nightly_export", ROOT / "scripts" / "nightly_export.py")
nightly = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(nightly)


def make_engine(path: Path):
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def add_event(engine, timestamp, event_id, tags=None):
    with Session(engine) as session:
        session.add(TelemetryEventTable(
            id=event_id, timestamp=timestamp, service="api", event_type="test",
            level="info", value=None, message=event_id, tags=tags or {},
        ))
        session.commit()


def _process_claim(database_url, target_iso, barrier, results, stale_before=None):
    process_engine = create_engine(
        database_url, connect_args={"check_same_thread": False, "timeout": 10}
    )
    barrier.wait()
    results.put(acquire_processing_lock(
        "nightly_export", date.fromisoformat(target_iso), process_engine,
        stale_before=stale_before,
    ))
    process_engine.dispose()


def _process_run_nightly(database_url, target_iso, output_dir, barrier,
                         runner_started, release_runner, results):
    process_engine = create_engine(
        database_url, connect_args={"check_same_thread": False, "timeout": 10}
    )
    barrier.wait()

    def fake_runner(*args, **kwargs):
        marker = Path(output_dir) / "pipeline-invoked"
        with marker.open("a", encoding="utf-8") as handle:
            handle.write("invoked\n")
        runner_started.set()
        if not release_runner.wait(timeout=15):
            raise TimeoutError("test runner release was not signalled")
        return type("Completed", (), {"returncode": 0})()

    try:
        result = nightly.run_nightly(
            date.fromisoformat(target_iso), engine=process_engine,
            output_dir=Path(output_dir), pipeline_runner=fake_runner,
        )
        results.put(("ok", result))
    except Exception as exc:
        results.put(("error", repr(exc)))
    finally:
        process_engine.dispose()


def test_target_date_parsing_and_utc_default(monkeypatch):
    assert nightly.resolve_target_date("2025-01-15") == date(2025, 1, 15)
    monkeypatch.setenv("TARGET_DATE", "not-a-date")
    import pytest
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        nightly.resolve_target_date()
    monkeypatch.delenv("TARGET_DATE")
    now = datetime(2026, 10, 13, 0, 30, tzinfo=timezone(timedelta(hours=2)))
    assert nightly.resolve_target_date(None, now) == date(2026, 10, 11)


def test_dotenv_is_loaded_without_overriding_process_environment(tmp_path, monkeypatch):
    from dotenv import load_dotenv as real_load_dotenv

    dotenv_path = tmp_path / "backend.env"
    dotenv_path.write_text(
        "DATABASE_URL=sqlite:///from-dotenv.db\nTARGET_DATE=2025-01-15\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("TARGET_DATE", "2025-01-16")

    import os

    calls = []

    def fake_dotenv_loader(path, override):
        calls.append((Path(path), override))
        return real_load_dotenv(dotenv_path, override=override)

    monkeypatch.setattr(nightly, "load_dotenv", fake_dotenv_loader)
    monkeypatch.setattr(nightly, "resolve_target_date",
                        lambda: date(2025, 1, 16))
    monkeypatch.setattr(nightly, "init_db", lambda: calls.append("init_db"))
    monkeypatch.setattr(nightly, "run_nightly", lambda target: "completed")
    monkeypatch.setattr(nightly, "configure_logging", lambda: None)

    assert nightly.main() == 0
    assert calls == [(nightly.API_DIR / ".env", False), "init_db"]
    assert os.environ["DATABASE_URL"] == "sqlite:///from-dotenv.db"
    assert os.environ["TARGET_DATE"] == "2025-01-16"


def test_stale_cutoff_default_and_config(monkeypatch):
    now = datetime(2025, 4, 1, 12, tzinfo=timezone.utc)
    monkeypatch.delenv("NIGHTLY_STALE_LOCK_MINUTES", raising=False)
    assert nightly.stale_lock_cutoff(now) == now - timedelta(hours=12)
    monkeypatch.setenv("NIGHTLY_STALE_LOCK_MINUTES", "90")
    assert nightly.stale_lock_cutoff(now) == now - timedelta(minutes=90)
    monkeypatch.setenv("NIGHTLY_STALE_LOCK_MINUTES", "0")
    with pytest.raises(ValueError, match="positive integer"):
        nightly.stale_lock_cutoff(now)


def test_recent_processing_is_not_stale_reclaimable(tmp_path):
    engine = make_engine(tmp_path / "recent.sqlite")
    target = date(2025, 4, 2)
    assert acquire_processing_lock("nightly_export", target, engine)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    assert not acquire_processing_lock(
        "nightly_export", target, engine, stale_before=cutoff
    )
    with Session(engine) as session:
        row = session.exec(select(JobRun).where(
            JobRun.target_date == target)).one()
        assert row.status == "processing"
        assert row.error_message is None


def test_stale_processing_is_recovered_atomically_and_refreshes_fields(tmp_path):
    engine = make_engine(tmp_path / "stale.sqlite")
    target = date(2025, 4, 3)
    old_started = datetime.now(timezone.utc) - timedelta(days=2)
    create_or_get_job("nightly_export", target, engine)
    with Session(engine) as session:
        row = session.exec(select(JobRun).where(
            JobRun.target_date == target)).one()
        row.status = "processing"
        row.started_at = old_started
        row.finished_at = old_started
        row.error_message = "previous worker was interrupted"
        session.add(row)
        session.commit()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    assert acquire_processing_lock(
        "nightly_export", target, engine, stale_before=cutoff
    )
    with Session(engine) as session:
        recovered = session.exec(select(JobRun).where(
            JobRun.target_date == target)).one()
        assert recovered.status == "processing"
        assert recovered.started_at > old_started
        assert recovered.finished_at is None
        assert recovered.error_message == "Recovered stale processing attempt"


def test_two_processes_competing_to_recover_stale_lock_have_one_winner(tmp_path):
    database_path = tmp_path / "stale-race.sqlite"
    engine = make_engine(database_path)
    target = date(2025, 4, 4)
    create_or_get_job("nightly_export", target, engine)
    with Session(engine) as session:
        row = session.exec(select(JobRun).where(
            JobRun.target_date == target)).one()
        row.status = "processing"
        row.started_at = datetime.now(timezone.utc) - timedelta(days=2)
        session.add(row)
        session.commit()

    context = multiprocessing.get_context("fork")
    barrier = context.Barrier(2)
    results = context.Queue()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    url = f"sqlite:///{database_path}"
    workers = [
        context.Process(
            target=_process_claim,
            args=(url, target.isoformat(), barrier, results, cutoff),
        )
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    outcomes = [results.get(timeout=15) for _ in workers]
    for worker in workers:
        worker.join(timeout=15)
        assert worker.exitcode == 0
    assert sorted(outcomes) == [False, True]
    with Session(engine) as session:
        row = session.exec(select(JobRun).where(
            JobRun.target_date == target)).one()
        assert row.status == "processing"
        assert row.error_message == "Recovered stale processing attempt"


def test_completed_row_is_not_reclaimed_by_stale_lock(tmp_path):
    engine = make_engine(tmp_path / "completed.sqlite")
    target = date(2025, 4, 5)
    assert acquire_processing_lock("nightly_export", target, engine)
    mark_completed("nightly_export", target, engine)
    old_cutoff = datetime.now(timezone.utc) + timedelta(days=1)
    assert not acquire_processing_lock(
        "nightly_export", target, engine, stale_before=old_cutoff
    )
    calls = []
    assert nightly.run_nightly(
        target, engine=engine, output_dir=tmp_path,
        pipeline_runner=lambda *a, **k: calls.append(a),
    ) == "skipped"
    assert calls == []


def test_concurrent_run_nightly_invokes_pipeline_once_and_publishes_one_csv(tmp_path):
    database_path = tmp_path / "full-flow.sqlite"
    engine = make_engine(database_path)
    target = date(2025, 4, 6)
    add_event(engine, datetime(2025, 4, 6, 1, tzinfo=timezone.utc), "event-1")

    context = multiprocessing.get_context("fork")
    barrier = context.Barrier(2)
    runner_started = context.Event()
    release_runner = context.Event()
    results = context.Queue()
    output_dir = tmp_path / "concurrent-raw"
    url = f"sqlite:///{database_path}"
    workers = [
        context.Process(
            target=_process_run_nightly,
            args=(url, target.isoformat(), str(output_dir), barrier,
                  runner_started, release_runner, results),
        )
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    first_outcome = None
    try:
        assert runner_started.wait(
            timeout=15), "pipeline runner was never entered"
        first_outcome = results.get(timeout=15)
        assert first_outcome == ("ok", "locked")
    finally:
        release_runner.set()
    remaining = results.get(timeout=15)
    outcomes = [first_outcome, remaining]
    for worker in workers:
        worker.join(timeout=15)
        assert worker.exitcode == 0

    assert sorted(outcomes) == [("ok", "completed"), ("ok", "locked")]
    marker = output_dir / "pipeline-invoked"
    assert marker.read_text(encoding="utf-8").splitlines() == ["invoked"]
    assert list(output_dir.glob("telemetry_*.csv")) == [
        output_dir / "telemetry_2025-04-06.csv"
    ]
    with Session(engine) as session:
        row = session.exec(select(JobRun).where(
            JobRun.target_date == target)).one()
        assert row.status == "completed"


def test_states_completed_idempotency_and_failed_retry(tmp_path):
    engine = make_engine(tmp_path / "state.sqlite")
    target = date(2025, 1, 15)
    row = create_or_get_job("nightly_export", target, engine)
    assert row.status == "pending"
    assert acquire_processing_lock("nightly_export", target, engine)
    assert has_processing_lock("nightly_export", target, engine)
    mark_completed("nightly_export", target, engine)
    assert has_completed_for_date("nightly_export", target, engine)
    calls = []
    assert nightly.run_nightly(target, engine=engine, output_dir=tmp_path,
                               pipeline_runner=lambda *a, **k: calls.append(a)) == "skipped"
    assert calls == []

    retry_date = date(2025, 1, 16)
    assert acquire_processing_lock("nightly_export", retry_date, engine)
    mark_failed("nightly_export", retry_date, "safe failure", engine)
    assert acquire_processing_lock("nightly_export", retry_date, engine)
    mark_completed("nightly_export", retry_date, engine)
    with Session(engine) as session:
        retry = session.exec(select(JobRun).where(
            JobRun.target_date == retry_date)).one()
        assert retry.status == "completed"
        assert retry.finished_at is not None


def test_csv_interval_columns_json_and_no_overwrite(tmp_path):
    engine = make_engine(tmp_path / "events.sqlite")
    target = date(2025, 1, 15)
    start = datetime(2025, 1, 15, tzinfo=timezone.utc)
    add_event(engine, start - timedelta(microseconds=1), "before")
    add_event(engine, start, "at-start", {"z": 2, "a": "yes"})
    add_event(engine, start + timedelta(hours=23, minutes=59), "inside")
    add_event(engine, start + timedelta(days=1), "at-end")
    path, created = nightly.export_telemetry_csv(
        target, tmp_path / "raw", engine)
    assert created
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert reader.fieldnames == [
            "id", "timestamp", "service", "event_type", "level", "value", "message", "tags"]
    assert [row["id"] for row in rows] == ["at-start", "inside"]
    assert rows[0]["timestamp"] == "2025-01-15T00:00:00Z"
    assert rows[0]["tags"] == '{"a":"yes","z":2}'
    original = path.read_text()
    path.write_text("existing backup\n")
    again, was_created = nightly.export_telemetry_csv(
        target, tmp_path / "raw", engine)
    assert again == path and not was_created
    assert path.read_text() == "existing backup\n"
    assert original


def test_pipeline_success_failure_and_csv_is_not_passed(tmp_path):
    engine = make_engine(tmp_path / "pipeline.sqlite")
    successful = date(2025, 2, 1)
    seen = []

    def success(command, **kwargs):
        seen.append((command, kwargs))
        return type("Completed", (), {"returncode": 0})()

    assert nightly.run_nightly(
        successful, engine=engine, output_dir=tmp_path / "raw", pipeline_runner=success) == "completed"
    command, kwargs = seen[0]
    assert command[-1].endswith("data/pipelines/pipeline.py")
    assert "csv" not in " ".join(command).lower()
    assert kwargs["cwd"] == str(ROOT)
    assert has_completed_for_date("nightly_export", successful, engine)

    failed = date(2025, 2, 2)
    import pytest
    with pytest.raises(RuntimeError, match="exited with code 7"):
        nightly.run_nightly(
            failed, engine=engine, output_dir=tmp_path / "raw",
            pipeline_runner=lambda *a, **k: type(
                "Completed", (), {"returncode": 7})(),
        )
    with Session(engine) as session:
        row = session.exec(select(JobRun).where(
            JobRun.target_date == failed)).one()
        assert row.status == "failed" and row.finished_at is not None
        assert "code 7" in row.error_message


def test_atomic_shared_file_sqlite_lock_has_one_winner(tmp_path):
    database_path = tmp_path / "shared.sqlite"
    engine = make_engine(database_path)
    target = date(2025, 3, 3)
    context = multiprocessing.get_context("fork")
    barrier = context.Barrier(2)
    results = context.Queue()
    url = f"sqlite:///{database_path}"
    workers = [
        context.Process(
            target=_process_claim,
            args=(url, target.isoformat(), barrier, results),
        )
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    outcomes = [results.get(timeout=15) for _ in workers]
    for worker in workers:
        worker.join(timeout=15)
        assert worker.exitcode == 0
    assert sorted(outcomes) == [False, True]
    assert has_processing_lock("nightly_export", target, engine)
    tables = inspect(engine).get_table_names()
    assert "job_runs" in tables
    indexes = inspect(engine).get_indexes("job_runs")
    assert any(index["column_names"] == ["job_name", "target_date"]
               for index in indexes)
    constraints = inspect(engine).get_unique_constraints("job_runs")
    assert any(item["column_names"] == ["job_name", "target_date"]
               for item in constraints)


def test_init_db_registers_job_runs_on_existing_engine(tmp_path, monkeypatch):
    from services.api import database

    database.reset_engine_for_tests()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'init.sqlite'}")
    monkeypatch.delenv("APP_ENV", raising=False)
    database.init_db()
    engine = database.get_engine()
    assert "job_runs" in inspect(engine).get_table_names()
    database.reset_engine_for_tests()
