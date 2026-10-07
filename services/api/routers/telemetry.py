"""Telemetry event ingestion with Supabase/PostgreSQL storage.

Accepts frontend/backend-produced telemetry events, validates each one
individually, and stores valid events in the ``telemetry_events`` table.

Key behaviour:
------------------
* The envelope is ``{"events": [ … ]}`` — a JSON array of event objects.
* Per-event validation via ``TelemetryEvent.model_validate()`` — an invalid
  event does NOT cancel the batch.
* Valid events are inserted in a single bulk INSERT.
* Duplicate ``eventId`` values (replayed events) are silently skipped — first
  write wins.
* The response reports N received, M stored, R rejected.
* Events are immutable once stored — no UPDATE path exists.
"""

import logging
from collections import Counter
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from database import get_db
from telemetry_models import TelemetryEvent as TelemetryEventTable


logger = logging.getLogger("api.telemetry")

router = APIRouter(tags=["telemetry"])


# ──────────────────────────────────────────────
# Pydantic validation model
# ──────────────────────────────────────────────


class TelemetryEvent(BaseModel):
    """Common envelope for every telemetry event.

    Mirrors the ``commonEnvelopeProperties`` schema defined in
    ``docs/telemetry/event-schemas.json``.
    """

    eventId: UUID
    timestamp: datetime
    sessionId: Optional[UUID] = None
    userId: Optional[UUID] = None
    event_type: str
    schemaVersion: str
    requestId: Optional[UUID] = None
    properties: dict[str, Any]


# ──────────────────────────────────────────────
# Storage helpers
# ──────────────────────────────────────────────


def _store_events(db_session: Session, valid_events: list[TelemetryEvent]) -> int:
    """Bulk-insert valid events into telemetry_events.

    Returns the number of rows actually inserted.  Duplicate PKs (replayed
    eventId) are silently skipped — the first insertion wins.
    """
    if not valid_events:
        return 0

    rows: list[TelemetryEventTable] = []
    for ev in valid_events:
        rows.append(
            TelemetryEventTable(
                event_id=str(ev.eventId),
                timestamp=ev.timestamp,
                event_type=ev.event_type,
                session_id=str(ev.sessionId) if ev.sessionId else None,
                user_id=str(ev.userId) if ev.userId else None,
                schema_version=ev.schemaVersion,
                request_id=str(ev.requestId) if ev.requestId else None,
                tags=ev.properties,
            )
        )

    # Bulk insert — SQLModel/SQLAlchemy 2.0 style.
    for row in rows:
        db_session.add(row)

    try:
        db_session.commit()
    except Exception:
        db_session.rollback()
        # If a bulk insert fails (e.g. PK conflict), fall back to
        # row-by-row insertion so that a single duplicate does not
        # discard the entire batch.
        stored = 0
        for row in rows:
            try:
                db_session.add(row)
                db_session.commit()
                stored += 1
            except Exception:
                db_session.rollback()
        return stored

    return len(rows)


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────


@router.post("/events")
async def receive_events(
    request: Request,
    db_session: Session = Depends(get_db),
):
    """Receive, validate and store a batch of telemetry events.

    Per-event validation means an invalid event is rejected individually
    without cancelling the rest of the batch.

    Returns:
        ``{"received": N, "stored": M, "rejected": R}``
    """
    # Read the raw body so we can validate per-event rather than letting
    # FastAPI reject the whole batch on the first invalid event.
    body = await request.json()

    raw_events = body.get("events", [])
    if not isinstance(raw_events, list):
        raw_events = []
    received = len(raw_events)

    if received == 0:
        return {"received": 0, "stored": 0, "rejected": 0}

    # Per-event validation — invalid events are rejected individually.
    valid_events: list[TelemetryEvent] = []
    rejected = 0

    for raw in raw_events:
        try:
            ev = TelemetryEvent.model_validate(raw)
            valid_events.append(ev)
        except ValidationError:
            rejected += 1

    stored = _store_events(db_session, valid_events)

    type_counts = dict(Counter(e.event_type for e in valid_events))
    logger.info(
        "Telemetry: received=%d stored=%d rejected=%d types=%s",
        received,
        stored,
        rejected,
        type_counts,
    )

    return {
        "received": received,
        "stored": stored,
        "rejected": rejected,
    }