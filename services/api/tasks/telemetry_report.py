"""Asynchronous telemetry report generation task."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

from celery import Task
from celery.utils.time import get_exponential_backoff_interval
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlmodel import Session

from celery_app import celery_app
from database import get_engine
from telemetry.report import build_telemetry_report, resolve_report_window

logger = logging.getLogger("api.tasks.telemetry_report")


class TelemetryReportTask(Task):
    """Retry transient database failures and route exhausted tasks to DLQ."""

    autoretry_for = ()
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 60
    retry_jitter = True
    acks_late = True

    def on_retry(self, exc: BaseException, task_id: str, args: tuple, kwargs: dict, einfo: Any) -> None:
        logger.warning(
            "telemetry_report retry task_id=%s attempt=%s max_retries=%s error_type=%s",
            task_id,
            self.request.retries + 1,
            self.max_retries,
            type(exc).__name__,
        )

    def on_failure(self, exc: BaseException, task_id: str, args: tuple, kwargs: dict, einfo: Any) -> None:
        logger.error(
            "telemetry_report permanent_failure task_id=%s attempt=%s error_type=%s",
            task_id,
            self.request.retries + 1,
            type(exc).__name__,
        )
        # Redis has no broker-native dead-letter exchange. Explicitly enqueue a
        # sanitized, JSON-only failure record into this dedicated Celery queue.
        dead_letter_task.apply_async(
            kwargs={
                "original_task_id": task_id,
                "task_name": self.name or "tasks.telemetry_report.generate_telemetry_report",
                "error_type": type(exc).__name__,
                "message": _safe_error_message(exc),
                "failed_at": date.today().isoformat(),
            },
            queue="dead_letter",
        )


def _safe_error_message(exc: BaseException) -> str:
    """Return a bounded error string with URL-like tokens removed."""
    import re

    message = str(exc)[:300]
    message = re.sub(r"[a-zA-Z][a-zA-Z0-9+.-]*://\S+",
                     "[redacted-url]", message)
    message = re.sub(
        r"(?i)(password|token|secret|credential|database_url|redis_url|api_key|access_key)(\s*[=:]\s*)\S+",
        r"\1\2[redacted]",
        message,
    )
    return message


def _retry_countdown(retries: int) -> int:
    """Calculate bounded exponential delay with the configured full jitter."""
    return get_exponential_backoff_interval(
        factor=1,
        retries=retries,
        maximum=TelemetryReportTask.retry_backoff_max,
        full_jitter=TelemetryReportTask.retry_jitter,
    )


@celery_app.task(bind=True, base=TelemetryReportTask, name="tasks.telemetry_report.generate_telemetry_report")
def generate_telemetry_report(
    self: TelemetryReportTask,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Compute and return a serializable telemetry report with an owned DB session."""
    task_id = self.request.id or "unknown"
    attempt = self.request.retries + 1
    started = time.monotonic()
    logger.info("telemetry_report started task_id=%s attempt=%s",
                task_id, attempt)

    try:
        start, end, start_bound, end_bound = resolve_report_window(
            start_date, end_date)
    except (TypeError, ValueError) as exc:
        logger.error("telemetry_report permanent_failure task_id=%s error_type=%s",
                     task_id, type(exc).__name__)
        raise

    try:
        # Each worker execution owns and closes an independent SQLModel session.
        with Session(get_engine()) as session:
            result = build_telemetry_report(
                session, start_bound, end_bound, start, end)
    except (OperationalError, DBAPIError) as exc:
        if self.request.retries < self.max_retries:
            logger.warning(
                "telemetry_report retry_requested task_id=%s attempt=%s error_type=%s",
                task_id,
                attempt,
                type(exc).__name__,
            )
            raise self.retry(
                exc=exc,
                countdown=_retry_countdown(self.request.retries),
            )
        raise

    logger.info(
        "telemetry_report succeeded task_id=%s attempt=%s duration_seconds=%.3f",
        task_id,
        attempt,
        time.monotonic() - started,
    )
    return result


@celery_app.task(name="tasks.telemetry_report.dead_letter")
def dead_letter_task(
    original_task_id: str,
    task_name: str,
    error_type: str,
    message: str,
    failed_at: str,
) -> dict[str, str]:
    """Store a minimal terminal failure record on the dedicated dead_letter queue."""
    record = {
        "original_task_id": original_task_id,
        "task_name": task_name,
        "error_type": error_type,
        "message": message,
        "failed_at": failed_at,
    }
    logger.error("dead_letter recorded task_id=%s task_name=%s",
                 original_task_id, task_name)
    return record


dead_letter_task.queue = "dead_letter"
