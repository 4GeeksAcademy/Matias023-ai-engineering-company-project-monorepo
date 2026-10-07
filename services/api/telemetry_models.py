"""Telemetry ORM models (Phase 3 — Event Storage).

Stores ingested telemetry events in the relational database
(PostgreSQL/Supabase when DATABASE_URL is set, SQLite for local dev).

Schema (8 columns):
------------------------------
* ``event_id`` — UUID v4 primary key, application-level deduplication key.
  A replayed batch with the same eventId fails the PK constraint.
* ``timestamp`` — when the event occurred (ISO 8601 UTC).
* ``event_type`` — classification key (e.g. page_viewed, incident_created).
* ``session_id`` — browser/device session UUID (nullable).
* ``user_id`` — actor user UUID (nullable, pseudonymous).
* ``schema_version`` — envelope + properties schema version.
* ``request_id`` — API request correlation UUID (nullable).
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
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import JSON, Field, SQLModel


class TelemetryEvent(SQLModel, table=True):
    """An ingested telemetry event, stored immutably.

    Maps 1:1 to the ``commonEnvelopeProperties`` schema defined in
    ``docs/telemetry/event-schemas.json``.
    """

    __tablename__ = "telemetry_events"

    event_id: str = Field(
        primary_key=True,
        nullable=False,
        description="UUID v4 from the envelope — application-level dedup key",
    )
    timestamp: datetime = Field(
        index=True,
        nullable=False,
        description="When the event occurred (from envelope)",
    )
    event_type: str = Field(
        index=True,
        nullable=False,
        description="Event classification key (e.g. page_viewed, incident_created)",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Browser/device session UUID (nullable)",
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Actor user UUID — pseudonymous, never email or doc_id (nullable)",
    )
    schema_version: str = Field(
        nullable=False,
        description="Envelope + properties schema version (e.g. 1.0)",
    )
    request_id: Optional[str] = Field(
        default=None,
        description="API request correlation UUID (nullable for frontend-only events)",
    )
    tags: dict = Field(
        default={},
        sa_type=JSON,
        nullable=False,
        description="Event-specific properties payload (jsonb on PostgreSQL, text on SQLite)",
    )