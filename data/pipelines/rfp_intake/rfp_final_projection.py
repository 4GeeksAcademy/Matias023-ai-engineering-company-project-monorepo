"""Map persisted RFP records to final-document input."""

from .rfp_final_document import (
    FinalDocumentBlocked,
    generate_final_document,
)

DEPARTMENTS = {"warehouse", "lastmile", "reverse"}


def project_section(section):
    """Use persisted, explicitly verified section values."""
    evaluation = section.evaluation_results or {}

    if evaluation.get("generation_status") != "completed":
        raise FinalDocumentBlocked(
            f"Generation incomplete: {section.department_id}"
        )

    if not evaluation.get("review_status"):
        raise FinalDocumentBlocked(
            f"Evaluation missing: {section.department_id}"
        )

    projected = {
        "approval_status": section.approval_status,
        "draft_content": section.draft_content,
        "approver": section.approver,
        "approved_at": (
            section.approved_at.isoformat()
            if section.approved_at else None
        ),
        "currency": evaluation.get("currency"),
    }

    # Only structured, explicitly verified commercial facts
    # may participate in arbitration. Never infer them from prose.
    verified = evaluation.get("verified_commercial_metrics")

    if isinstance(verified, dict):
        for key in (
            "monthly_capacity",
            "monthly_volume",
            "returns_turnaround_hours",
        ):
            value = verified.get(key)
            if (
                type(value) in (int, float)
                and value >= 0
                and value != float("inf")
            ):
                projected[key] = value

    return projected


def build_from_persisted_records(ticket, metadata, sections):
    """Validate DB records and consolidate active departments."""
    if ticket.status != "esperando_aprobación":
        raise FinalDocumentBlocked(
            "Ticket is not awaiting final approval"
        )

    if metadata.ticket_id != ticket.ticket_id:
        raise FinalDocumentBlocked("Metadata ticket mismatch")

    active = list(metadata.departments_needed or [])

    if (
        not active
        or len(active) != len(set(active))
        or any(dept not in DEPARTMENTS for dept in active)
    ):
        raise FinalDocumentBlocked(
            "Invalid active department configuration"
        )

    mapped = {}

    for section in sections:
        if section.ticket_id != ticket.ticket_id:
            raise FinalDocumentBlocked("Section ticket mismatch")

        if section.department_id in mapped:
            raise FinalDocumentBlocked(
                "Duplicate department section"
            )

        mapped[section.department_id] = project_section(section)

    if set(mapped) != set(active):
        raise FinalDocumentBlocked(
            "Persisted sections do not match active departments"
        )

    return generate_final_document(
        ticket.ticket_id,
        metadata.client_country,
        active,
        mapped,
    )
