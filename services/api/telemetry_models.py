"""Telemetry ORM models (Phase 3 — Event Storage).

Stores ingested telemetry events in the relational database
(PostgreSQL/Supabase when DATABASE_URL is set, SQLite for local dev).

Schema (8 columns):
------------------------------
* ``id`` — UUID primary key, auto-generated with gen_random_uuid().
* ``timestamp`` — when the event occurred (timestamptz, required).
* ``service`` — originating service name (text, required).
* ``event_type`` — classification key (e.g. page_viewed, incident_created).
* ``level`` — event severity level (text, default "info", values: info/warn/error).
* ``value`` — numeric value extracted from properties (numeric, nullable).
* ``message`` — human-readable event summary (text, nullable).
* ``tags`` — event-specific properties as JSONB (PostgreSQL) / TEXT (SQLite).

Indexes:
------------------------------
* ``timestamp`` — B-tree for time-range queries.
* ``event_type`` — B-tree for type-filtered queries.
* ``tags`` — GIN on PostgreSQL for JSON key/value lookups (created in
  ``database.py`` init_db because SQLModel does not support GIN natively).

Immutability:
------------------------------
Events are immutable once inserted — there is no UPDATE path.

Telemetry plan requires deduplication via ``eventId`` from the envelope.
The implementation uses a pre-insert query to skip existing eventIds
(which are stored inside ``tags``).

Schema alignment with the official 4Geeks exercise specification:
  | Column    | PostgreSQL type          | Notes                              |
  |-----------|--------------------------|------------------------------------|
  | id        | uuid PK gen_random_uuid  | Auto-generated, separate from eventId |
  | timestamp | timestamptz NOT NULL     | B-tree index                       |
  | service   | text NOT NULL            | Derived: "api" or "backoffice"     |
  | event_type| text NOT NULL            | B-tree index                       |
  | level     | text DEFAULT 'info'      | Values: info, warn, error          |
  | value     | numeric NULL             | Extracted from properties          |
  | message   | text NULL                | Human-readable summary             |
  | tags      | jsonb DEFAULT '{}'       | GIN index, stores eventId etc.     |
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from sqlalchemy import JSON, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# Use JSONB on PostgreSQL (for GIN index support), plain JSON on other dialects
# like SQLite (where it's stored as TEXT).
_TAGS_TYPE = JSON().with_variant(JSONB(), "postgresql")


class TelemetryEventTable(SQLModel, table=True):
    """An ingested telemetry event, stored immutably.

    Uses an auto-generated UUID primary key. Original envelope fields
    (eventId, sessionId, userId, schemaVersion, requestId) are preserved
    inside ``tags`` for auditability.
    """

    __tablename__ = "telemetry_events"

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        primary_key=True,
        nullable=False,
        description="UUID v4 — generated in Python for portability across PostgreSQL and SQLite",
    )
    timestamp: datetime = Field(
        index=True,
        nullable=False,
        description="When the event occurred (ISO 8601 UTC)",
    )
    service: str = Field(
        nullable=False,
        description="Originating service name (e.g. backoffice, api)",
    )
    event_type: str = Field(
        index=True,
        nullable=False,
        description="Event classification key (e.g. page_viewed, incident_created)",
    )
    level: str = Field(
        default="info",
        nullable=False,
        description="Event severity level (info, warn, error)",
    )
    value: Optional[Decimal] = Field(
        default=None,
        nullable=True,
        sa_type=Numeric(12, 4),
        description="Numeric value extracted from event properties",
    )
    message: Optional[str] = Field(
        default=None,
        nullable=True,
        description="Human-readable event summary",
    )
    tags: dict = Field(
        default={},
        sa_type=_TAGS_TYPE,
        nullable=False,
        description="Event-specific properties payload (jsonb on PostgreSQL, text on SQLite)",
    )