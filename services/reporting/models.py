"""SQLModel tables for weekly business performance and pipeline run metadata.

PostgreSQL stores these in the dedicated ``reporting`` schema. SQLite uses
portable unqualified table names for local development and automated tests.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, Integer, JSON, MetaData, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import registry
from sqlmodel import Field, SQLModel


REPORTING_REGISTRY = registry(metadata=MetaData())


class ReportingBase(SQLModel, registry=REPORTING_REGISTRY):
    """SQLModel base with isolated metadata for reporting-owned tables."""


def _uuid_column():
    """Return portable UUID storage (native UUID in PostgreSQL, text in SQLite)."""
    return PG_UUID(as_uuid=False).with_variant(String(36), "sqlite")


class WeeklyWarehouseClientPerformance(ReportingBase, table=True):
    """Aggregated KPI row at warehouse + client + ISO-week grain."""

    __tablename__ = "weekly_warehouse_client_performance"
    __table_args__ = (
        UniqueConstraint(
            "warehouse", "client_id", "week_start", name="uq_weekly_performance_grain"
        ),
        {"schema": "reporting"},
    )

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(_uuid_column(), primary_key=True,
                         default=lambda: str(uuid4())),
    )
    warehouse: str = Field(sa_type=String, nullable=False)
    client_id: str = Field(sa_type=String, nullable=False)
    week_start: date = Field(nullable=False)
    inbound_units_count: int = Field(
        default=0, sa_type=Integer, nullable=False)
    outbound_orders_count: int = Field(
        default=0, sa_type=Integer, nullable=False)
    stockout_events_count: int = Field(
        default=0, sa_type=Integer, nullable=False)
    discrepancy_events_count: int = Field(
        default=0, sa_type=Integer, nullable=False)
    discrepancy_rate: Decimal = Field(
        default=Decimal("0"), sa_type=Numeric, nullable=False)
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True),
                         nullable=False, server_default=func.now()),
    )


class PipelineRun(ReportingBase, table=True):
    """Safe operational metadata for one pipeline execution."""

    __tablename__ = "pipeline_runs"
    __table_args__ = (
        Index("ix_pipeline_runs_pipeline_week", "pipeline_name", "week_start"),
        {"schema": "reporting"},
    )

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        sa_column=Column(_uuid_column(), primary_key=True,
                         default=lambda: str(uuid4())),
    )
    pipeline_name: str = Field(sa_type=String, nullable=False, index=True)
    week_start: date = Field(nullable=False, index=True)
    state: str = Field(default="Running", sa_type=String, nullable=False)
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Optional[datetime] = Field(
        default=None, sa_type=DateTime(timezone=True))
    events_read: int = Field(default=0, sa_type=Integer, nullable=False)
    events_rejected: int = Field(default=0, sa_type=Integer, nullable=False)
    events_rejected_reasons: dict = Field(
        default_factory=dict, sa_type=JSON, nullable=False)
    groups_aggregated: int = Field(default=0, sa_type=Integer, nullable=False)
    rows_upserted: int = Field(default=0, sa_type=Integer, nullable=False)
    retry_count: int = Field(default=0, sa_type=Integer, nullable=False)
    error_summary: Optional[str] = Field(default=None, sa_type=String)


def create_reporting_tables(engine) -> None:
    """Create reporting tables on the shared, configured application engine.

    SQLite ``get_engine`` connections translate the PostgreSQL ``reporting``
    schema to the default namespace. PostgreSQL retains schema qualification.
    """
    ReportingBase.metadata.create_all(engine)
