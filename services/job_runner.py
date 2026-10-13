"""Portable state and atomic-lock operations for background jobs."""

from datetime import date, datetime, timezone
import re
from typing import Optional

from sqlalchemy import and_, case, insert, or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from services.api.database import get_engine
from services.job_models import JobRun


def _engine(engine=None):
    return engine if engine is not None else get_engine()


def create_or_get_job(job_name: str, target_date: date, engine=None) -> JobRun:
    """Ensure the unique job/date row exists and return its current record.

    The unique constraint resolves simultaneous first-time inserts; callers
    must still use :func:`acquire_processing_lock` before doing any work.
    """
    db_engine = _engine(engine)
    with Session(db_engine) as session:
        values = {
            "job_name": job_name,
            "target_date": target_date,
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
        }
        # Native conflict-do-nothing is an atomic insert-if-absent on both
        # supported databases and avoids SQLite's read-to-write race.
        if db_engine.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert

            statement = dialect_insert(JobRun).values(**values).on_conflict_do_nothing(
                index_elements=["job_name", "target_date"]
            )
        elif db_engine.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert

            statement = dialect_insert(JobRun).values(**values).on_conflict_do_nothing(
                index_elements=["job_name", "target_date"]
            )
        else:
            statement = insert(JobRun).values(**values)
        try:
            session.exec(statement)
            session.commit()
        except IntegrityError:
            session.rollback()  # Fallback for an unsupported dialect.
        row = session.exec(
            select(JobRun).where(
                JobRun.job_name == job_name, JobRun.target_date == target_date
            )
        ).one()
        session.expunge(row)
        return row


def has_processing_lock(job_name: str, target_date: date, engine=None) -> bool:
    with Session(_engine(engine)) as session:
        return session.exec(
            select(JobRun.id).where(
                JobRun.job_name == job_name,
                JobRun.target_date == target_date,
                JobRun.status == "processing",
            )
        ).first() is not None


def has_completed_for_date(job_name: str, target_date: date, engine=None) -> bool:
    with Session(_engine(engine)) as session:
        return session.exec(
            select(JobRun.id).where(
                JobRun.job_name == job_name,
                JobRun.target_date == target_date,
                JobRun.status == "completed",
            )
        ).first() is not None


def acquire_processing_lock(
    job_name: str,
    target_date: date,
    engine=None,
    *,
    stale_before: Optional[datetime] = None,
) -> bool:
    """Atomically claim an unclaimed or stale job; exactly one caller wins.

    A processing row is reclaimable only when it has a recorded start time
    older than ``stale_before``. The conditional UPDATE is the lock operation
    for both initial claims and stale recovery on SQLite and PostgreSQL.
    """
    db_engine = _engine(engine)
    create_or_get_job(job_name, target_date, db_engine)
    now = datetime.now(timezone.utc)
    stale_processing = and_(
        JobRun.status == "processing",
        JobRun.started_at.is_not(None),
        JobRun.started_at < stale_before,
    ) if stale_before is not None else None
    claimable_status = (
        or_(JobRun.status.in_(("pending", "failed")), stale_processing)
        if stale_processing is not None
        else JobRun.status.in_(("pending", "failed"))
    )
    values = {
        "status": "processing",
        "started_at": now,
        "finished_at": None,
    }
    if stale_processing is not None:
        values["error_message"] = case(
            (stale_processing, "Recovered stale processing attempt"),
            else_=None,
        )
    with Session(db_engine) as session:
        result = session.exec(
            update(JobRun)
            .where(
                JobRun.job_name == job_name,
                JobRun.target_date == target_date,
                claimable_status,
            )
            .values(**values)
        )
        session.commit()
        return result.rowcount == 1


def _transition(
    job_name: str,
    target_date: date,
    status: str,
    error_message: Optional[str] = None,
    engine=None,
) -> None:
    if status not in {"completed", "failed"}:
        raise ValueError(f"Unsupported terminal job status: {status}")
    safe_message = _safe_error(error_message) if error_message else None
    with Session(_engine(engine)) as session:
        result = session.exec(
            update(JobRun)
            .where(
                JobRun.job_name == job_name,
                JobRun.target_date == target_date,
                JobRun.status == "processing",
            )
            .values(
                status=status,
                finished_at=datetime.now(timezone.utc),
                error_message=safe_message,
            )
        )
        session.commit()
        if result.rowcount != 1:
            raise RuntimeError(
                f"Cannot transition {job_name}/{target_date} to {status}: "
                "the job is not processing"
            )


def mark_completed(job_name: str, target_date: date, engine=None) -> None:
    _transition(job_name, target_date, "completed", engine=engine)


def mark_failed(
    job_name: str, target_date: date, error_message: str, engine=None
) -> None:
    _transition(job_name, target_date, "failed", error_message, engine)


def _safe_error(message: str) -> str:
    """Avoid persisting URL-style credentials in diagnostic text."""
    text = str(message)
    text = re.sub(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s]+", "[redacted-url]", text)
    return text[:2000]
