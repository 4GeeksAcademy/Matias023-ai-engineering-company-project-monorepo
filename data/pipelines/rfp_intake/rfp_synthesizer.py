"""Consolidate validated TrackFlow department analyses."""

from .rfp_orchestrator import plan_departments


def synthesize_departments(
    departments_needed: list[str],
    results: list[dict],
) -> dict:
    """Consolidate exactly the requested departments."""

    plan = plan_departments(departments_needed)

    if not isinstance(results, list):
        raise ValueError("Department results must be a list")

    by_department = {}

    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Invalid department result")

        department = result.get("department_id")

        if department in by_department:
            raise ValueError("Duplicate department result")

        if not isinstance(result.get("draft_content"), str):
            raise ValueError("Missing department draft")

        if not result["draft_content"].strip():
            raise ValueError("Empty department draft")

        if not result.get("evidence"):
            raise ValueError("Missing department evidence")

        by_department[department] = result

    expected = {item["department_id"] for item in plan}

    if set(by_department) != expected:
        raise ValueError("Department results do not match plan")

    sections = []
    for item in plan:
        department = item["department_id"]
        result = by_department[department]

        sections.append({
            "department_id": department,
            "owner": item["owner"],
            "key_aspects": result["key_aspects"],
            "draft_content": result["draft_content"],
            "evidence": result["evidence"],
            "unconfirmed": result.get("unconfirmed", []),
        })

    return {
        "status": "ready_for_review",
        "departments_completed": len(sections),
        "sections": sections,
    }
