"""Telemetry event ingestion with Supabase/PostgreSQL storage.

Accepts frontend/backend-produced telemetry events, validates each one
individually, and stores valid events in the ``telemetry_events`` table.

Key behaviour:
------------------
* The envelope is ``{"events": [ … ]}`` — a JSON array of event objects.
* Per-event validation via ``TelemetryEvent.model_validate()`` — an invalid
  event does NOT cancel the batch.
* Valid events are inserted in a single bulk INSERT.
* Duplicate ``eventId`` values are checked via pre-insert query — first write wins.
* The response reports N received, M stored, R rejected.
* Events are immutable once stored — no UPDATE path exists.
"""

import logging
from collections import Counter
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select
from sqlalchemy import insert, text

from database import get_db
from telemetry_models import TelemetryEventTable


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
# Service derivation
# ──────────────────────────────────────────────

# Backend-produced events (from api.py routers)
_BACKEND_EVENT_TYPES: set[str] = {
    "incident_created",
    "incident_status_transition",
    "api_validation_error",
    "api_server_error",
    "inventory_query_duration",
    "sku_created",
    "inbound_registered",
    "outbound_registered",
    "outbound_insufficient_stock",
    "warehouse_mismatch_rejected",
    "sku_duplicate_rejected",
    "login_succeeded",
    "user_registered",
    "supplier_status_changed",
}


def _derive_service(event: TelemetryEvent) -> str:
    """Derive the originating service name.

    Backend-produced events use ``"api"``.
    Frontend-produced events (backoffice web app) use ``"backoffice"``.
    """
    if event.event_type in _BACKEND_EVENT_TYPES:
        return "api"
    return "backoffice"


# ──────────────────────────────────────────────
# Level derivation
# ──────────────────────────────────────────────

_ERROR_EVENT_TYPES: set[str] = {
    "api_server_error",
    "api_validation_error",
    "frontend_error_captured",
    "login_failed",
}

_WARNING_EVENT_TYPES: set[str] = {
    "outbound_insufficient_stock",
    "warehouse_mismatch_rejected",
    "sku_duplicate_rejected",
}


def _derive_level(event: TelemetryEvent) -> str:
    """Derive the severity level from the event type.

    Allowed values per exercise spec: info, warn, error.
    Fallback is ``"info"``.
    """
    if event.event_type in _ERROR_EVENT_TYPES:
        return "error"
    if event.event_type in _WARNING_EVENT_TYPES:
        return "warn"
    return "info"


# ──────────────────────────────────────────────
# Value extraction
# ──────────────────────────────────────────────

_NUMERIC_PROPERTY_KEYS: dict[str, str] = {
    "inventory_query_duration": "duration_ms",
    "outbound_insufficient_stock": "shortfall",
    "outbound_registered": "quantity",
    "inbound_registered": "quantity",
}


def _extract_value(event: TelemetryEvent) -> Optional[Decimal]:
    """Extract a numeric value from event properties if applicable.

    Returns ``None`` when no numeric value applies.
    The value is returned as Decimal to match the PostgreSQL ``numeric`` column type.
    """
    prop_key = _NUMERIC_PROPERTY_KEYS.get(event.event_type)
    if prop_key is not None:
        raw = event.properties.get(prop_key)
        if raw is not None:
            try:
                return Decimal(str(raw))
            except (ValueError, TypeError):
                return None
    return None


# ──────────────────────────────────────────────
# Message generation
# ──────────────────────────────────────────────


def _generate_message(event: TelemetryEvent) -> Optional[str]:
    """Generate a human-readable summary from event properties.

    Returns ``None`` when no message is applicable.
    """
    props = event.properties
    if not props:
        return None

    event_type = event.event_type

    # Page/view events
    if event_type == "page_viewed":
        page = props.get("page", "?")
        return f"Page viewed: {page}"

    # Incident events
    if event_type == "incident_created":
        cat = props.get("category", "?")
        branch = props.get("branch", "?")
        return f"Incident created: {cat} @ {branch}"

    if event_type == "incident_status_transition":
        prev_s = props.get("previous_status", "?")
        new_s = props.get("new_status", "?")
        return f"Incident status: {prev_s} → {new_s}"

    # Inventory events
    if event_type == "inbound_registered":
        sku = props.get("sku_code", "?")
        qty = props.get("quantity", "?")
        return f"Inbound: {qty}x {sku}"

    if event_type == "outbound_registered":
        sku = props.get("sku_code", "?")
        qty = props.get("quantity", "?")
        etype = props.get("exit_type", "?")
        return f"Outbound ({etype}): {qty}x {sku}"

    if event_type == "outbound_insufficient_stock":
        sku = props.get("sku_code", "?")
        short = props.get("shortfall", "?")
        return f"Insufficient stock: {sku} shortfall={short}"

    # Auth events
    if event_type == "login_succeeded":
        role = props.get("user_role", "?")
        return f"Login succeeded: role={role}"

    if event_type == "login_failed":
        reason = props.get("failure_reason", "?")
        return f"Login failed: {reason}"

    if event_type == "user_registered":
        return "User registered"

    # Supplier events
    if event_type == "supplier_status_changed":
        prev = props.get("previous_status", "?")
        new_s = props.get("new_status", "?")
        return f"Supplier status: {prev} → {new_s}"

    # Error events
    if event_type in ("api_server_error", "api_validation_error"):
        path = props.get("path", "?")
        code = props.get("error_code", "?")
        return f"{event_type}: {code} @ {path}"

    if event_type == "frontend_error_captured":
        kind = props.get("errorKind", "?")
        page = props.get("page", "?")
        return f"Frontend error: {kind} on {page}"

    # SKU events
    if event_type == "sku_created":
        sku = props.get("sku_code", "?")
        return f"SKU created: {sku}"

    if event_type == "warehouse_mismatch_rejected":
        sku = props.get("sku_code", "?")
        return f"Warehouse mismatch: {sku}"

    if event_type == "sku_duplicate_rejected":
        sku = props.get("sku_code", "?")
        return f"SKU duplicate rejected: {sku}"

    # Performance events
    if event_type == "inventory_query_duration":
        ep = props.get("endpoint", "?")
        ms = props.get("duration_ms", "?")
        return f"Query: {ep} ({ms}ms)"

    return None


# ──────────────────────────────────────────────
# Tags builder
# ──────────────────────────────────────────────


def _build_tags(event: TelemetryEvent) -> dict[str, Any]:
    """Build the ``tags`` JSONB column for a telemetry event.

    Preserves the original ``properties`` and also stores the envelope
    dimensions required by the telemetry plan (eventId, sessionId, userId,
    schemaVersion, requestId) inside tags so they are never lost.
    """
    tags: dict[str, Any] = dict(event.properties) if event.properties else {}

    # Store envelope dimensions inside tags for auditability
    tags["eventId"] = str(event.eventId)
    if event.sessionId:
        tags["sessionId"] = str(event.sessionId)
    if event.userId:
        tags["userId"] = str(event.userId)
    tags["schemaVersion"] = event.schemaVersion
    if event.requestId:
        tags["requestId"] = str(event.requestId)

    return tags


# ──────────────────────────────────────────────
# Deduplication
# ──────────────────────────────────────────────


def _is_duplicate(db_session: Session, event_id: str) -> bool:
    """Check if an eventId already exists in the telemetry_events table.

    The ``eventId`` is stored inside the ``tags`` JSONB column.
    Tries a SQL JSON operator first (PostgreSQL JSONB ``->>`` / newer SQLite).
    Falls back to Python-side iteration for older SQLite.
    """
    # Attempt SQL JSON operator first
    try:
        stmt = text(
            "SELECT 1 FROM telemetry_events WHERE tags->>'eventId' = :eid LIMIT 1"
        )
        result = db_session.exec(stmt, {"eid": event_id}).first()
        if result is not None:
            return True
        return False
    except Exception:
        pass

    # Fallback: iterate all rows Python-side.
    # Do NOT use LIMIT — we must check every row.
    stmt = select(TelemetryEventTable)
    rows = db_session.exec(stmt).all()
    for row in rows:
        if row.tags and row.tags.get("eventId") == event_id:
            return True
    return False


# ──────────────────────────────────────────────
# Storage helpers
# ──────────────────────────────────────────────


def _store_events(db_session: Session, valid_events: list[TelemetryEvent]) -> int:
    """Insert valid events into telemetry_events with deduplication.

    Uses a single bulk INSERT for performance. Duplicate ``eventId`` values
    (checked via pre-insert query against ``tags``) are skipped — first write wins.
    Returns the number of rows actually stored.
    """
    if not valid_events:
        return 0

    # Pre-filter: skip duplicates, generate id in Python (ORM-level
    # default_factory is not triggered during core-level bulk INSERT).
    rows_to_insert: list[dict] = []
    for ev in valid_events:
        if _is_duplicate(db_session, str(ev.eventId)):
            continue

        rows_to_insert.append({
            "id": str(uuid4()),
            "timestamp": ev.timestamp,
            "service": _derive_service(ev),
            "event_type": ev.event_type,
            "level": _derive_level(ev),
            "value": _extract_value(ev),
            "message": _generate_message(ev),
            "tags": _build_tags(ev),
        })

    if not rows_to_insert:
        return 0

    # Bulk insert — single statement, single commit
    try:
        db_session.execute(insert(TelemetryEventTable), rows_to_insert)
        db_session.commit()
    except Exception as exc:
        logger.warning("Bulk insert failed for %d events: %s", len(rows_to_insert), exc)
        db_session.rollback()
        return 0

    return len(rows_to_insert)


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