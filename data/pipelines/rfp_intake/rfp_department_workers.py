"""Department-specific instructions for TrackFlow RFP analysis."""

from .rfp_orchestrator import DEPARTMENT_OWNERS


DEPARTMENT_SCOPES = {
    "warehouse": (
        "Analyze storage, inventory, receiving, picking, "
        "packing and fulfillment requirements."
    ),
    "lastmile": (
        "Analyze final delivery, geographic coverage, "
        "distribution and delivery requirements."
    ),
    "reverse": (
        "Analyze product returns, reverse logistics, "
        "inspection and returned goods handling."
    ),
}


def build_department_assignment(
    department_id: str,
    markdown: str,
) -> dict[str, str]:
    """Prepare a department assignment using only source material."""

    if department_id not in DEPARTMENT_SCOPES:
        raise ValueError(f"Unknown department: {department_id}")

    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("RFP document is empty")

    return {
        "department_id": department_id,
        "owner": DEPARTMENT_OWNERS[department_id],
        "scope": DEPARTMENT_SCOPES[department_id],
        "instructions": (
            "Analyze only the assigned department. "
            "Extract requirements explicitly supported by the RFP. "
            "Do not invent costs, operational capabilities, "
            "deadlines, SLA commitments or commercial conditions. "
            "Mark missing information as not confirmed. "
            "Use exact evidence from the original document."
        ),
        "document": markdown,
    }

from pydantic import BaseModel, ConfigDict, Field


class DepartmentAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_aspects: list[str] = Field(min_length=1)
    draft_content: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    unconfirmed: list[str] = Field(default_factory=list)


def analyze_department(
    department_id: str,
    markdown: str,
    *,
    client=None,
    model: str | None = None,
) -> dict:
    """Analyze one department and validate source evidence."""
    import os
    from google import genai
    from google.genai import types

    assignment = build_department_assignment(
        department_id, markdown
    )

    selected_model = model or os.getenv("GEMINI_MODEL")
    if not selected_model:
        raise ValueError("GEMINI_MODEL must be configured")

    if client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        client = genai.Client(api_key=api_key)

    instruction = (
        assignment["scope"] + "\n" +
        assignment["instructions"] + "\n"
        "Return a JSON object with these keys: "
        "key_aspects (list of requirements), "
        "draft_content (analysis, not a commercial promise), "
        "evidence (exact excerpts from the supplied document), "
        "unconfirmed (missing information). "
        "Every factual claim must be supported by document evidence. "
        "Do not invent prices, capacities or SLAs. "
        "Do not use information from outside the document."
    )

    response = client.models.generate_content(
        model=selected_model,
        contents=assignment["document"],
        config=types.GenerateContentConfig(
            system_instruction=instruction,
            temperature=0,
            response_mime_type="application/json",
        ),
    )

    if not response.text:
        raise ValueError("Department agent returned empty response")

    result = DepartmentAnalysis.model_validate_json(response.text)

    for excerpt in result.evidence:
        if not excerpt.strip() or excerpt not in markdown:
            raise ValueError(
                "Department evidence not found in document"
            )

    return {
        "department_id": department_id,
        "owner": assignment["owner"],
        **result.model_dump(),
    }
