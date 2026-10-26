"""Persist validated RFP classification in PostgreSQL."""

from sqlmodel import Session, select

from database import get_engine
from rfp_lifecycle import transition_ticket
from rfp_models import RFPTicket, RFPMetadata


def persist_rfp_classification(
    ticket_id: str,
    classification,
    readability_metrics: dict,
) -> dict:
    """Store classification atomically without completing valid RFP analysis."""

    engine = get_engine()
    if engine.dialect.name != "postgresql":
        raise RuntimeError("RFP classification requires PostgreSQL")

    with Session(engine) as session:
        with session.begin():
            ticket = session.exec(
                select(RFPTicket)
                .where(RFPTicket.ticket_id == ticket_id)
                .with_for_update()
            ).one_or_none()

            if ticket is None:
                raise ValueError("RFP ticket not found")

            if ticket.status != "analizando":
                raise ValueError("RFP ticket is no longer analyzing")

            existing = session.exec(
                select(RFPMetadata).where(
                    RFPMetadata.ticket_id == ticket_id
                )
            ).first()

            if existing is not None:
                raise ValueError("RFP classification already persisted")

            if not classification.is_rfp:
                transition_ticket(ticket, "descartado")
                session.add(ticket)

                return {
                    "ticket_id": ticket_id,
                    "status": "descartado",
                    "rfp_id": None,
                    "departments_needed": [],
                }

            metadata = RFPMetadata(
                ticket_id=ticket_id,
                client_name=classification.client_name,
                client_country=classification.client_country,
                services_requested=classification.services_requested,
                monthly_volume=classification.monthly_volume,
                deadline=classification.deadline,
                budget_range=classification.budget_range,
                departments_needed=classification.departments_needed,
                readability_metrics=readability_metrics,
            )

            session.add(metadata)
            session.flush()

            ticket.rfp_id = metadata.rfp_id
            session.add(ticket)

            return {
                "ticket_id": ticket_id,
                "status": ticket.status,
                "rfp_id": metadata.rfp_id,
                "departments_needed": metadata.departments_needed,
            }
