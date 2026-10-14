"""HTTP endpoints for submitting and observing Celery tasks."""

from __future__ import annotations

import re
from typing import Any

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException, Query, status

from celery_app import celery_app
from tasks.telemetry_report import generate_telemetry_report

router = APIRouter(tags=["tasks"])


@router.post("/telemetry/report", status_code=status.HTTP_202_ACCEPTED)
def enqueue_telemetry_report(
    start_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> dict[str, str]:
    """Queue telemetry report generation and return the Celery task ID."""
    from telemetry.report import resolve_report_window

    try:
        resolve_report_window(start_date, end_date)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = generate_telemetry_report.apply_async(kwargs={
        "start_date": start_date,
        "end_date": end_date,
    })
    return {"task_id": result.id, "status": "PENDING"}


def _sanitize_error(value: Any) -> str:
    """Reduce a Celery failure to a bounded, credential-safe message."""
    message = str(value)[:500]
    message = re.sub(r"[a-zA-Z][a-zA-Z0-9+.-]*://\S+",
                     "[redacted-url]", message)
    message = re.sub(
        r"(?i)(password|token|secret|credential|database_url|redis_url|api_key|access_key)(\s*[=:]\s*)\S+",
        r"\1\2[redacted]",
        message,
    )
    return message


@router.get("/{task_id}")
def get_task_status(task_id: str) -> dict[str, Any]:
    """Return the current Celery result-backend state for a task."""
    if not task_id or len(task_id) > 200:
        raise HTTPException(status_code=400, detail="Invalid task_id")

    result = AsyncResult(task_id, app=celery_app)
    response: dict[str, Any] = {"task_id": task_id, "status": result.state}
    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = _sanitize_error(result.result)
    return response
