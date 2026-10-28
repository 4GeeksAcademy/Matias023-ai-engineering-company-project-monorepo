"""Ticket state transitions for TrackFlow RFP intake, Part 1."""

from datetime import datetime, timezone

from rfp_models import RFPTicket


ALLOWED_TRANSITIONS = {
    "analizando": {"analisis_completo", "descartado"},
    "analisis_completo": {"generando_borrador"},
    "generando_borrador": {"en_evaluación", "needs_human_review"},
    "en_evaluación": {
        "generando_borrador",
        "needs_human_review",
        "esperando_aprobación",
    },
    "needs_human_review": {"esperando_aprobación"},
    "esperando_aprobación": {"generando_borrador", "terminado"},
    "terminado": set(),
    "descartado": set(),
}


def transition_ticket(ticket: RFPTicket, new_status: str) -> RFPTicket:
    """Validate and apply a TrackFlow RFP status transition."""
    allowed = ALLOWED_TRANSITIONS.get(ticket.status)

    if allowed is None:
        raise ValueError("Unknown current ticket status")

    if new_status not in allowed:
        raise ValueError(
            f"Invalid RFP status transition: {ticket.status} -> {new_status}"
        )

    ticket.status = new_status
    ticket.updated_at = datetime.now(timezone.utc)
    return ticket
