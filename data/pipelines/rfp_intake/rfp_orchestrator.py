"""Deterministic department selection for TrackFlow RFPs."""

from typing import Any

DEPARTMENT_OWNERS = {
    "warehouse": "Ana Whitfield",
    "lastmile": "Carlos Vega",
    "reverse": "Sofía Ramos",
}


def plan_departments(
    departments_needed: list[str],
) -> list[dict[str, Any]]:
    """Build an ordered plan for departments explicitly requested."""

    if not isinstance(departments_needed, list):
        raise ValueError("departments_needed must be a list")

    if len(departments_needed) != len(set(departments_needed)):
        raise ValueError("Duplicate departments are not allowed")

    if not departments_needed:
        raise ValueError("No departments selected for orchestration")

    plan = []

    for department in departments_needed:
        if department not in DEPARTMENT_OWNERS:
            raise ValueError(f"Unknown department: {department}")

        plan.append({
            "department_id": department,
            "owner": DEPARTMENT_OWNERS[department],
        })

    return plan
