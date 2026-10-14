"""Unit and API tests for async telemetry reports (no Redis required)."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import tasks as task_router
from tasks import telemetry_report as task_module


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_enqueue_returns_202_and_task_id(client, monkeypatch):
    apply_async = Mock(return_value=SimpleNamespace(id="celery-task-123"))
    monkeypatch.setattr(task_router.generate_telemetry_report,
                        "apply_async", apply_async)

    response = client.post(
        "/tasks/telemetry/report?start_date=2026-10-01&end_date=2026-10-10"
    )

    assert response.status_code == 202
    assert response.json()["task_id"] == "celery-task-123"
    apply_async.assert_called_once_with(kwargs={
        "start_date": "2026-10-01",
        "end_date": "2026-10-10",
    })


def test_enqueue_rejects_inverted_dates(client, monkeypatch):
    apply_async = Mock()
    monkeypatch.setattr(task_router.generate_telemetry_report,
                        "apply_async", apply_async)
    response = client.post(
        "/tasks/telemetry/report?start_date=2026-10-10&end_date=2026-10-01"
    )
    assert response.status_code == 422
    apply_async.assert_not_called()


def test_task_status_returns_success_result(client, monkeypatch):
    monkeypatch.setattr(
        task_router,
        "AsyncResult",
        lambda task_id, app: SimpleNamespace(
            state="SUCCESS", result={"metrics": {}}),
    )
    response = client.get("/tasks/report-123")
    assert response.status_code == 200
    assert response.json() == {
        "task_id": "report-123",
        "status": "SUCCESS",
        "result": {"metrics": {}},
    }


def test_task_failure_is_sanitized(client, monkeypatch):
    error = "failed connecting postgresql://user:secret@db.example/db password=hunter2"
    monkeypatch.setattr(
        task_router,
        "AsyncResult",
        lambda task_id, app: SimpleNamespace(state="FAILURE", result=error),
    )
    response = client.get("/tasks/report-failed")
    body = response.json()
    assert body["status"] == "FAILURE"
    assert "secret" not in body["error"]
    assert "hunter2" not in body["error"]
    assert "postgresql://" not in body["error"]
    assert "traceback" not in body


@pytest.mark.parametrize("state", ["PENDING", "STARTED", "RETRY"])
def test_task_status_returns_nonterminal_state(client, monkeypatch, state):
    monkeypatch.setattr(
        task_router,
        "AsyncResult",
        lambda task_id, app: SimpleNamespace(state=state, result=None),
    )
    assert client.get("/tasks/report-pending").json() == {
        "task_id": "report-pending",
        "status": state,
    }


def test_retry_policy_is_three_attempts_with_backoff():
    assert task_module.TelemetryReportTask.max_retries == 3
    assert task_module.TelemetryReportTask.retry_backoff is True
    assert task_module.TelemetryReportTask.retry_jitter is True


def test_final_failure_is_sent_to_dead_letter_queue(monkeypatch):
    enqueue_dead_letter = Mock()
    monkeypatch.setattr(
        task_module.dead_letter_task,
        "apply_async",
        enqueue_dead_letter,
    )
    failure = RuntimeError(
        "database unavailable at postgresql://user:secret@db.example/db"
    )

    task_module.TelemetryReportTask.on_failure(
        task_module.generate_telemetry_report,
        failure,
        "celery-task-failed",
        (),
        {},
        None,
    )

    enqueue_dead_letter.assert_called_once()
    options = enqueue_dead_letter.call_args.kwargs
    assert options["queue"] == "dead_letter"
    assert options["kwargs"]["original_task_id"] == "celery-task-failed"
    assert "secret" not in options["kwargs"]["message"]


def test_dead_letter_message_redacts_database_and_redis_urls():
    message = task_module._safe_error_message(RuntimeError(
        "database_url=postgresql://db.example/db redis_url=redis://cache/0"
    ))
    assert "postgresql://" not in message
    assert "redis://" not in message
    assert "database_url=[redacted]" in message
    assert "redis_url=[redacted]" in message


def test_retry_countdown_uses_exponential_full_jitter(monkeypatch):
    get_backoff = Mock(return_value=2)
    monkeypatch.setattr(
        task_module, "get_exponential_backoff_interval", get_backoff)

    assert task_module._retry_countdown(2) == 2
    get_backoff.assert_called_once_with(
        factor=1,
        retries=2,
        maximum=60,
        full_jitter=True,
    )


def test_task_opens_its_own_sqlmodel_session(monkeypatch):
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    engine = object()
    monkeypatch.setattr(task_module, "get_engine", Mock(return_value=engine))
    session_factory = Mock(return_value=session)
    monkeypatch.setattr(task_module, "Session", session_factory)
    monkeypatch.setattr(
        task_module,
        "build_telemetry_report",
        Mock(return_value={"period": {}, "metrics": {}}),
    )

    task_module.generate_telemetry_report.run(
        start_date="2026-10-01",
        end_date="2026-10-10",
    )

    task_module.get_engine.assert_called_once_with()
    session_factory.assert_called_once_with(engine)
    task_module.build_telemetry_report.assert_called_once()
    assert isinstance(date.fromisoformat("2026-10-01"), date)
