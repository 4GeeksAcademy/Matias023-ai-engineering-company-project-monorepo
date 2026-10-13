#!/usr/bin/env python3
"""Export a UTC telemetry-day backup, then run the existing weekly pipeline.

The CSV is an audit/recovery artifact only. The pipeline continues to query
its normal database inputs and is launched independently as a subprocess.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time as time_module
from typing import Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "services" / "api"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from dotenv import load_dotenv
from sqlmodel import Session, select

from telemetry_models import TelemetryEventTable
from services.api.database import get_engine, init_db
from services.job_runner import (
    _safe_error,
    acquire_processing_lock,
    create_or_get_job,
    has_completed_for_date,
    has_processing_lock,
    mark_completed,
    mark_failed,
)

JOB_NAME = "nightly_export"
DEFAULT_STALE_LOCK_MINUTES = 720
CSV_COLUMNS = [
    "id", "timestamp", "service", "event_type", "level", "value", "message", "tags"
]
LOGGER = logging.getLogger("nightly_export")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)sZ level=%(levelname)s job_name=%(job_name)s "
        "target_date=%(target_date)s status=%(status)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # logging's formatter uses local time; ensure emitted timestamp is UTC.
    logging.Formatter.converter = time_module.gmtime


def _log(level: int, target_date: date, status: str, message: str, *args) -> None:
    LOGGER.log(
        level,
        message,
        *args,
        extra={"job_name": JOB_NAME, "target_date": target_date.isoformat(),
               "status": status},
    )


def stale_lock_cutoff(now: Optional[datetime] = None) -> datetime:
    """Return UTC stale cutoff; default is a conservative twelve hours."""
    raw_minutes = os.environ.get(
        "NIGHTLY_STALE_LOCK_MINUTES", str(DEFAULT_STALE_LOCK_MINUTES)
    )
    try:
        minutes = int(raw_minutes)
    except ValueError as exc:
        raise ValueError(
            "NIGHTLY_STALE_LOCK_MINUTES must be a positive integer") from exc
    if minutes <= 0:
        raise ValueError(
            "NIGHTLY_STALE_LOCK_MINUTES must be a positive integer")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(timezone.utc) - timedelta(minutes=minutes)


def resolve_target_date(value: Optional[str] = None, now: Optional[datetime] = None) -> date:
    """Parse TARGET_DATE or return yesterday according to the UTC calendar."""
    raw = os.environ.get("TARGET_DATE") if value is None else value
    if raw is not None:
        try:
            parsed = date.fromisoformat(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "TARGET_DATE must be a valid date in YYYY-MM-DD format") from exc
        if parsed.isoformat() != raw:
            raise ValueError(
                "TARGET_DATE must be a valid date in YYYY-MM-DD format")
        return parsed
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(timezone.utc).date() - timedelta(days=1)


def _as_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def export_telemetry_csv(target_date: date, output_dir: Path, engine=None) -> tuple[Path, bool]:
    """Create the daily CSV only when absent; return path and created flag."""
    from sqlalchemy import and_

    db_engine = engine if engine is not None else get_engine()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"telemetry_{target_date.isoformat()}.csv"
    if destination.exists():
        return destination, False

    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    with Session(db_engine) as session:
        events = session.exec(
            select(TelemetryEventTable)
            .where(
                and_(
                    TelemetryEventTable.timestamp >= start,
                    TelemetryEventTable.timestamp < end,
                )
            )
            .order_by(TelemetryEventTable.timestamp, TelemetryEventTable.id)
        ).all()

    # Build a complete snapshot beside its destination, then publish via an
    # atomic hard link, which fails rather than overwriting a competing file.
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=output_dir,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as temp_file:
            temp_name = temp_file.name
            writer = csv.DictWriter(
                temp_file, fieldnames=CSV_COLUMNS, lineterminator="\n")
            writer.writeheader()
            for event in events:
                writer.writerow({
                    "id": event.id,
                    "timestamp": _as_utc_iso(event.timestamp),
                    "service": event.service,
                    "event_type": event.event_type,
                    "level": event.level,
                    "value": "" if event.value is None else str(event.value),
                    "message": "" if event.message is None else event.message,
                    "tags": json.dumps(event.tags or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                })
            temp_file.flush()
            os.fsync(temp_file.fileno())
        try:
            os.link(temp_name, destination)
            created = True
        except FileExistsError:
            created = False
        return destination, created
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def run_nightly(
    target_date: date,
    *,
    engine=None,
    output_dir: Optional[Path] = None,
    pipeline_runner: Optional[Callable[...,
                                       subprocess.CompletedProcess]] = None,
) -> str:
    """Run the orchestration, returning completed/skipped/locked or raising."""
    db_engine = engine if engine is not None else get_engine()
    create_or_get_job(JOB_NAME, target_date, db_engine)
    _log(logging.INFO, target_date, "started", "Nightly job starting")
    # A completed job is terminal and is never eligible for stale recovery.
    if has_completed_for_date(JOB_NAME, target_date, db_engine):
        _log(logging.INFO, target_date, "skipped",
             "Already completed; skipping export and pipeline")
        return "skipped"
    stale_before = stale_lock_cutoff()
    if not acquire_processing_lock(
        JOB_NAME, target_date, db_engine, stale_before=stale_before
    ):
        state = "processing" if has_processing_lock(
            JOB_NAME, target_date, db_engine) else "locked"
        _log(logging.INFO, target_date, state,
             "Job is already processing or was claimed concurrently; skipping")
        return "locked"

    _log(logging.INFO, target_date, "processing", "Acquired processing lock")
    try:
        csv_path, created = export_telemetry_csv(
            target_date, output_dir or (REPO_ROOT / "data" / "raw"), db_engine
        )
        _log(
            logging.INFO, target_date, "processing",
            "CSV backup generated: %s" if created else "CSV backup reused: %s", csv_path,
        )
        command = [sys.executable, str(
            REPO_ROOT / "data" / "pipelines" / "pipeline.py")]
        _log(logging.INFO, target_date, "processing",
             "Starting pipeline subprocess")
        runner = pipeline_runner or subprocess.run
        completed = runner(command, cwd=str(REPO_ROOT), check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                f"Pipeline subprocess exited with code {completed.returncode}")
        _log(logging.INFO, target_date, "processing",
             "Pipeline subprocess finished successfully")
        mark_completed(JOB_NAME, target_date, db_engine)
        _log(logging.INFO, target_date, "completed", "Nightly job completed")
        return "completed"
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        try:
            mark_failed(JOB_NAME, target_date, message, db_engine)
        except Exception as transition_exc:
            _log(logging.ERROR, target_date, "failed",
                 "Could not persist failed state: %s", type(transition_exc).__name__)
        _log(logging.ERROR, target_date, "failed",
             "Nightly job failed: %s", _safe_error(message))
        raise


def main() -> int:
    configure_logging()
    # Match the backend's .env source for standalone cron execution. Existing
    # process environment variables (including TARGET_DATE) take precedence.
    load_dotenv(REPO_ROOT / "services" / "api" / ".env", override=False)
    try:
        target_date = resolve_target_date()
    except ValueError as exc:
        # Target date invalidity is reported before any DB access or job creation.
        LOGGER.error(
            "timestamp=%s job_name=%s target_date=%s status=invalid %s",
            datetime.now(timezone.utc).isoformat(), JOB_NAME,
            os.environ.get("TARGET_DATE", "<unset>"), exc,
            extra={"job_name": JOB_NAME,
                   "target_date": os.environ.get("TARGET_DATE", "<unset>"),
                   "status": "invalid"},
        )
        return 2
    try:
        init_db()
        run_nightly(target_date)
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
