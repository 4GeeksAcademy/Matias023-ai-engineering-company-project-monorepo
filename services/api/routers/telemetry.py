"""Telemetry event ingestion stub.

Accepts frontend-produced telemetry events and acknowledges receipt.
No database writes — this is a pure ingestion endpoint that logs
received events for downstream observability (future enhancement).

Environment variables (reserved for future use):
    TELEMETRY_ENDPOINT — external sink URL for forwarding telemetry events.
"""

import logging
from collections import Counter
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel


logger = logging.getLogger("api.telemetry")

router = APIRouter(tags=["telemetry"])


# ──────────────────────────────────────────────
# Pydantic models
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


class TelemetryBatch(BaseModel):
    """Batch of telemetry events sent from a single producer."""

    events: list[TelemetryEvent]


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────


@router.post("/events")
def receive_events(batch: TelemetryBatch):
    """Receive and acknowledge a batch of telemetry events.

    This is a write-only ingestion endpoint:
      * validates the batch against the common envelope schema
      * logs the received count and unique event types
      * returns ``{"received": N}`` — no database writes, no persistence.

    Future: forward to ``TELEMETRY_ENDPOINT`` external sink.
    """
    count = len(batch.events)

    if count > 0:
        type_counts = dict(Counter(e.event_type for e in batch.events))
        logger.info("Telemetry: received %d event(s), types=%s", count, type_counts)
    else:
        logger.info("Telemetry: received empty batch")

    return {"received": count}