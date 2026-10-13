"""ORM model for standalone background-job orchestration."""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel


JOB_STATUSES = ("pending", "processing", "completed", "failed")


class JobRun(SQLModel, table=True):
    """One orchestration run per job name and target date."""

    __tablename__ = "job_runs"
    __table_args__ = (
        Index("ix_job_runs_job_name_target_date", "job_name", "target_date"),
        UniqueConstraint("job_name", "target_date",
                         name="uq_job_runs_name_date"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_job_runs_status",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    job_name: str = Field(nullable=False, index=False, max_length=100)
    target_date: date = Field(nullable=False)
    status: str = Field(default="pending", nullable=False, max_length=20)
    started_at: Optional[datetime] = Field(default=None, nullable=True)
    finished_at: Optional[datetime] = Field(default=None, nullable=True)
    error_message: Optional[str] = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
