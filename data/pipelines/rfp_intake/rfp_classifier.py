"""Gemini-backed classification for TrackFlow RFP documents."""

import os

from google import genai
from google.genai import types

from pydantic import ConfigDict
from .classification_schema import RFPClassification


class GeminiResponseSchema(RFPClassification):
    # Gemini does not accept additionalProperties in response_schema.
    # Strict validation remains in RFPClassification.
    model_config = ConfigDict(extra="ignore")



SYSTEM_INSTRUCTION = """
You classify logistics documents received by TrackFlow.

An RFP is a client asking for logistics services or a proposal.
Accept both formal RFPs and informal client requests.
Reject vendor pitches, advertising and unrelated documents.

Available departments:
- warehouse: storage, fulfillment, inventory, picking and packing.
- lastmile: final delivery, carriers and distribution to recipients.
- reverse: returns, reverse logistics and returned goods processing.

Extract only facts explicitly supported by the document.
Never invent names, countries, volumes, budgets or deadlines.
Use null when a scalar value is absent.
Do not activate departments for services not requested.

Evidence must contain short, exact excerpts from the document
supporting the classification and requested services.

For non-RFP documents, use document_type="not_rfp",
is_rfp=false and departments_needed=[].

Return data matching the required schema.
"""


def classify_rfp(
    markdown: str,
    *,
    client=None,
    model: str | None = None,
) -> RFPClassification:
    """Classify document content using structured Gemini output."""

    if not markdown.strip():
        raise ValueError("Cannot classify an empty document")

    selected_model = model or os.getenv("GEMINI_MODEL")

    if not selected_model:
        raise ValueError("GEMINI_MODEL must be configured")

    if client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=selected_model,
        contents=markdown,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0,
            response_mime_type="application/json",
            response_schema=GeminiResponseSchema,
        ),
    )

    if not response.text:
        raise ValueError("Gemini returned no classification")

    result = RFPClassification.model_validate_json(response.text)

    if not result.evidence:
        raise ValueError("Classification has no textual evidence")

    for excerpt in result.evidence:
        if not excerpt.strip() or excerpt not in markdown:
            raise ValueError("Classification evidence not found in document")

    for field in (
        "client_name",
        "client_country",
        "deadline",
        "budget_range",
    ):
        value = getattr(result, field)
        if value is None:
            continue

        normalized_value = " ".join(value.casefold().split())

        supported = any(
            normalized_value in " ".join(quote.casefold().split())
            for quote in result.evidence
        )

        if not supported:
            raise ValueError(
                f"Unsupported extracted metadata: {field}"
            )

    import re
    import unicodedata

    def normalize(text):
        text = unicodedata.normalize("NFKD", text.casefold())
        return "".join(
            char for char in text
            if not unicodedata.combining(char)
        )

    evidence_text = normalize(" ".join(result.evidence))

    if result.monthly_volume is not None:
        numbers = re.findall(
            r"(?<!\w)\d[\d., ]*(?!\w)",
            evidence_text,
        )
        values = {
            int(re.sub(r"\D", "", number))
            for number in numbers
            if re.sub(r"\D", "", number)
        }
        if result.monthly_volume not in values:
            raise ValueError(
                "Unsupported extracted metadata: monthly_volume"
            )

    service_terms = {
        "warehouse": (
            "almacen", "bodega", "inventario",
            "picking", "packing", "fulfillment",
            "storage", "warehous",
        ),
        "lastmile": (
            "ultima milla", "last mile",
            "entrega", "distribucion", "delivery",
        ),
        "reverse": (
            "devolucion", "devoluciones",
            "logistica inversa", "retorno",
            "returns", "reverse logistics",
        ),
    }

    for department in result.departments_needed:
        for term in service_terms[department]:
            pattern = (
                r"\b(?:no\s+(?:necesitamos|requerimos|"
                r"solicitamos|queremos|incluimos)|sin)"
                r"\s+(?:\w+\s+){0,4}"
                + re.escape(term)
                + r"\b"
            )
            if re.search(pattern, evidence_text):
                raise ValueError(
                    f"Negated service requires review: {department}"
                )
        if not any(
            term in evidence_text
            for term in service_terms[department]
        ):
            raise ValueError(
                f"Unsupported department: {department}"
            )

    return result
