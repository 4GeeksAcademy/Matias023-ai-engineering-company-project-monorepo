"""Persistent TrackFlow RFP intake models (Hito 9)."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RFPTicket(SQLModel, table=True):
    __tablename__ = "rfp_tickets"

    ticket_id: str = Field(
        default_factory=lambda: str(uuid4()),
        primary_key=True,
    )
    rfp_id: str | None = Field(default=None, index=True)
    status: str = Field(default="analizando", index=True)
    raw_pdf_path: str
    owner_uuid: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class RFPMetadata(SQLModel, table=True):
    __tablename__ = "rfp_metadata"

    rfp_id: str = Field(
        default_factory=lambda: str(uuid4()),
        primary_key=True,
    )
    ticket_id: str = Field(
        foreign_key="rfp_tickets.ticket_id",
        index=True,
        unique=True,
    )
    client_name: str | None = None
    client_country: str | None = None
    services_requested: list = Field(
        default_factory=list,
        sa_type=JSON_TYPE,
    )
    monthly_volume: int | None = None
    deadline: str | None = None
    budget_range: str | None = None
    departments_needed: list = Field(
        default_factory=list,
        sa_type=JSON_TYPE,
    )
    readability_metrics: dict = Field(
        default_factory=dict,
        sa_type=JSON_TYPE,
    )


class RFPDepartmentSection(SQLModel, table=True):
    __tablename__ = "rfp_department_sections"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        primary_key=True,
    )
    ticket_id: str = Field(
        foreign_key="rfp_tickets.ticket_id",
        index=True,
    )
    department_id: str = Field(index=True)
    key_aspects: list = Field(
        default_factory=list,
        sa_type=JSON_TYPE,
    )
    draft_content: str | None = None
    evaluation_results: dict = Field(
        default_factory=dict,
        sa_type=JSON_TYPE,
    )
    approval_status: str | None = None
    approver: str | None = None
    approved_at: datetime | None = None



class RFPFinalDocument(SQLModel, table=True):
    """Final document persisted with its originating RFP ticket."""

    __tablename__ = "rfp_final_documents"

    ticket_id: str = Field(
        foreign_key="rfp_tickets.ticket_id",
        primary_key=True,
    )
    content: str
    generated_at: datetime = Field(default_factory=utcnow)
