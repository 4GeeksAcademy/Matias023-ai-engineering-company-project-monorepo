"""Authorization for TrackFlow RFP department approvals."""

import os

from fastapi import HTTPException

from data.pipelines.rfp_intake.rfp_approval_graph import APPROVERS


APPROVER_EMAIL_ENV = {
    "warehouse": "RFP_APPROVER_WAREHOUSE_EMAIL",
    "lastmile": "RFP_APPROVER_LASTMILE_EMAIL",
    "reverse": "RFP_APPROVER_REVERSE_EMAIL",
}


def authorize_department_approval(user, department_id: str) -> str:
    """Return the fixed approver name only for an authorized user."""

    if department_id not in APPROVERS:
        raise HTTPException(
            status_code=404,
            detail="Unknown RFP department",
        )

    expected_email = os.getenv(
        APPROVER_EMAIL_ENV[department_id], ""
    ).strip().casefold()

    if not expected_email:
        raise HTTPException(
            status_code=503,
            detail="Department approver is not configured",
        )

    if not getattr(user, "is_active", False):
        raise HTTPException(
            status_code=403,
            detail="Inactive user",
        )

    actual_email = (
        getattr(user, "email", "") or ""
    ).strip().casefold()

    if actual_email != expected_email:
        raise HTTPException(
            status_code=403,
            detail="User cannot approve this department",
        )

    return APPROVERS[department_id]


def authorize_ticket_read(user, ticket) -> None:
    """Only the active ticket creator can read confidential RFP data."""
    user_uuid = getattr(user, "uuid", None)
    owner_uuid = getattr(ticket, "owner_uuid", None)

    if (
        not getattr(user, "is_active", False)
        or not user_uuid
        or not owner_uuid
        or user_uuid != owner_uuid
    ):
        raise HTTPException(
            status_code=403,
            detail="Access to this RFP ticket is forbidden",
        )
