"""RFP commercial compliance regression tests."""

import pytest

from data.pipelines.rfp_intake.rfp_compliance import (
    check_commercial_rules,
)
from data.pipelines.rfp_intake.rfp_final_document import (
    FinalDocumentBlocked,
    generate_final_document,
)


def test_discount_keyword_without_table_is_rejected():
    draft = (
        "On-time delivery SLA 98%. "
        "We provide a volume discount table."
    )

    issues = check_commercial_rules(draft, "Spain")

    assert "Volume discount table missing or unconfirmed" in issues


@pytest.mark.parametrize(
    "header",
    [
        "| Monthly volume | Volume discount |",
        "| Volumen mensual | Descuento |",
    ],
)
def test_numeric_volume_discount_table_is_recognized(header):
    draft = (
        "On-time delivery SLA 98%.\n"
        f"{header}\n"
        "| --- | --- |\n"
        "| 1000 | 5% |"
    )

    issues = check_commercial_rules(draft, "Spain")

    assert "Volume discount table missing or unconfirmed" not in issues


def test_confidential_rate_blocks_final_document():
    sections = {
        "warehouse": {
            "approval_status": "approved",
            "draft_content": (
                "Approved proposal. "
                "Negotiated carrier rate EUR 12."
            ),
            "currency": "EUR",
            "approver": "SYNTHETIC APPROVER",
            "approved_at": "2026-01-01T00:00:00Z",
        },
    }

    with pytest.raises(
        FinalDocumentBlocked,
        match="Confidential carrier rate",
    ):
        generate_final_document(
            "SYNTHETIC-TICKET",
            "Spain",
            ["warehouse"],
            sections,
        )


def test_ordinary_approved_document_remains_eligible():
    sections = {
        "warehouse": {
            "approval_status": "approved",
            "draft_content": "Approved synthetic proposal.",
            "currency": "EUR",
            "approver": "SYNTHETIC APPROVER",
            "approved_at": "2026-01-01T00:00:00Z",
        },
    }

    document = generate_final_document(
        "SYNTHETIC-TICKET",
        "Spain",
        ["warehouse"],
        sections,
    )

    assert document["currency"] == "EUR"
    assert len(document["sections"]) == 1
