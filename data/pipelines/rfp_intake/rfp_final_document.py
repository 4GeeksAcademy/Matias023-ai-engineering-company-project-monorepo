"""Final RFP document consolidation for TrackFlow."""

from datetime import datetime, timezone
from math import isfinite
from typing import Any

from .rfp_arbitration import arbitrate


class FinalDocumentBlocked(ValueError):
    """The RFP is not eligible for final document generation."""


CURRENCY_BY_COUNTRY = {
    "españa": "EUR",
    "spain": "EUR",
    "estados unidos": "USD",
    "united states": "USD",
    "us": "USD",
    "usa": "USD",
}


def _valid_nonnegative_metric(value):
    """Accept nonnegative integers and finite nonnegative floats."""
    if type(value) is int:
        return value >= 0

    if type(value) is float:
        return isfinite(value) and value >= 0

    return False


def generate_final_document(
    ticket_id: str,
    client_country: str,
    active_departments: list[str],
    sections: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Consolidate only approved, conflict-free active departments."""

    country = (client_country or "").strip().casefold()
    currency = CURRENCY_BY_COUNTRY.get(country)

    if not currency:
        raise FinalDocumentBlocked(
            "Client country or currency mapping is unconfirmed"
        )

    if not active_departments or len(set(active_departments)) != len(
        active_departments
    ):
        raise FinalDocumentBlocked("Invalid active department list")

    consolidated = []

    for department in active_departments:
        section = sections.get(department)

        if not section:
            raise FinalDocumentBlocked(
                f"Missing active department: {department}"
            )

        if section.get("approval_status") != "approved":
            raise FinalDocumentBlocked(
                f"Department not approved: {department}"
            )

        draft = section.get("draft_content")
        if not isinstance(draft, str) or not draft.strip():
            raise FinalDocumentBlocked(
                f"Missing approved draft: {department}"
            )

        # Recheck explicit confidential-rate disclosures at export.
        # Human approval must not bypass this commercial safeguard.
        from .rfp_compliance import check_commercial_rules

        violations = check_commercial_rules(
            draft,
            client_country,
        )

        if "Potential disclosure of negotiated carrier rates" in violations:
            raise FinalDocumentBlocked(
                "Confidential carrier rate detected in approved draft"
            )

        consolidated.append({
            "department_id": department,
            "draft_content": draft,
            "approver": section.get("approver"),
            "approved_at": section.get("approved_at"),
        })

    active_sections = {
        dept: sections[dept] for dept in active_departments
    }

    for department, section in active_sections.items():
        if not section.get("currency"):
            raise FinalDocumentBlocked(
                f"Currency not verified: {department}"
            )

    if "warehouse" in active_sections and "lastmile" in active_sections:
        capacity = active_sections["warehouse"].get("monthly_capacity")
        volume = active_sections["lastmile"].get("monthly_volume")

        if not (
            _valid_nonnegative_metric(capacity)
            and _valid_nonnegative_metric(volume)
        ):
            raise FinalDocumentBlocked(
                "Warehouse capacity or Last Mile volume not verified"
            )

    if "reverse" in active_sections:
        turnaround = active_sections["reverse"].get(
            "returns_turnaround_hours"
        )

        if not _valid_nonnegative_metric(turnaround):
            raise FinalDocumentBlocked(
                "Returns SLA not verified"
            )

    conflicts = arbitrate(
        client_country,
        active_sections,
    )

    if conflicts:
        raise FinalDocumentBlocked(
            f"Unresolved arbitration conflicts: {conflicts}"
        )

    return {
        "ticket_id": ticket_id,
        "sections": consolidated,
        "currency": currency,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
