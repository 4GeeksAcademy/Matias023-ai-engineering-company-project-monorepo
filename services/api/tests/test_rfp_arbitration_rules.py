
"""Deterministic RFP arbitration regression tests."""

import pytest

from data.pipelines.rfp_intake.rfp_arbitration import arbitrate
from data.pipelines.rfp_intake.rfp_final_document import (
    FinalDocumentBlocked,
    generate_final_document,
)


@pytest.mark.parametrize(
    "sections,expected_trigger,expected_arbiter",
    [
        (
            {
                "warehouse": {
                    "currency": "EUR",
                    "monthly_capacity": 100,
                },
                "lastmile": {
                    "currency": "EUR",
                    "monthly_volume": 150,
                },
            },
            "volume-vs-capacity",
            "Miguel Torres",
        ),
        (
            {
                "reverse": {
                    "currency": "EUR",
                    "returns_turnaround_hours": 24,
                },
            },
            "returns-sla-breach",
            "Sofía Ramos",
        ),
        (
            {
                "warehouse": {
                    "currency": "USD",
                },
            },
            "currency-mismatch",
            "Miguel Torres",
        ),
    ],
)
def test_arbitration_conflicts(
    sections, expected_trigger, expected_arbiter
):
    conflicts = arbitrate("Spain", sections)

    assert len(conflicts) == 1
    assert conflicts[0]["trigger_id"] == expected_trigger
    assert conflicts[0]["arbiter"] == expected_arbiter
    assert conflicts[0]["decision"] == "request_changes"


def test_clean_arbitration():
    sections = {
        "warehouse": {
            "currency": "EUR",
            "monthly_capacity": 150,
        },
        "lastmile": {
            "currency": "EUR",
            "monthly_volume": 100,
        },
        "reverse": {
            "currency": "EUR",
            "returns_turnaround_hours": 48,
        },
    }

    assert arbitrate("Spain", sections) == []


@pytest.mark.parametrize(
    "invalid_value",
    [
        float("inf"),
        float("nan"),
    ],
)
def test_final_document_rejects_nonfinite_capacity(invalid_value):
    sections = {
        "warehouse": {
            "approval_status": "approved",
            "draft_content": "Synthetic warehouse draft",
            "approver": "Ana Whitfield",
            "approved_at": "2026-10-26",
            "currency": "EUR",
            "monthly_capacity": invalid_value,
        },
        "lastmile": {
            "approval_status": "approved",
            "draft_content": "Synthetic lastmile draft",
            "approver": "Carlos Vega",
            "approved_at": "2026-10-26",
            "currency": "EUR",
            "monthly_volume": 100,
        },
    }

    with pytest.raises(FinalDocumentBlocked):
        generate_final_document(
            "TEST-NONFINITE",
            "Spain",
            ["warehouse", "lastmile"],
            sections,
        )


@pytest.mark.parametrize(
    "department,metric,invalid_value",
    [
        ("lastmile", "monthly_volume", float("inf")),
        ("lastmile", "monthly_volume", float("nan")),
        ("reverse", "returns_turnaround_hours", float("inf")),
        ("reverse", "returns_turnaround_hours", float("nan")),
    ],
)
def test_final_document_rejects_nonfinite_other_metrics(
    department, metric, invalid_value
):
    """Reject nonfinite commercial values in active departments."""

    sections = {
        "warehouse": {
            "approval_status": "approved",
            "draft_content": "Synthetic warehouse proposal",
            "approver": "Ana Whitfield",
            "approved_at": "2026-10-26",
            "currency": "EUR",
            "monthly_capacity": 150,
        },
        "lastmile": {
            "approval_status": "approved",
            "draft_content": "Synthetic lastmile proposal",
            "approver": "Carlos Vega",
            "approved_at": "2026-10-26",
            "currency": "EUR",
            "monthly_volume": 100,
        },
        "reverse": {
            "approval_status": "approved",
            "draft_content": "Synthetic reverse proposal",
            "approver": "Sofía Ramos",
            "approved_at": "2026-10-26",
            "currency": "EUR",
            "returns_turnaround_hours": 48,
        },
    }

    sections[department][metric] = invalid_value

    with pytest.raises(FinalDocumentBlocked):
        generate_final_document(
            "TEST-NONFINITE-COMMERCIAL",
            "Spain",
            ["warehouse", "lastmile", "reverse"],
            sections,
        )



@pytest.mark.parametrize(
    "conflicts,clear,expected_triggers",
    [
        ([], True, []),
        (
            [{
                "trigger_id": "returns-sla-breach",
                "arbiter": "SYNTHETIC APPROVER",
                "private_note": "SECRET-COMMERCIAL-DATA",
            }],
            False,
            ["returns-sla-breach"],
        ),
    ],
)
def test_rfp_arbitration_trace_metadata_only(
    conflicts, clear, expected_triggers
):
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from agent_tracing import (
        read_trace,
        record_rfp_arbitration,
    )

    with TemporaryDirectory() as directory:
        trace_file = Path(directory) / "rfp-test.jsonl"

        run_id = record_rfp_arbitration(
            "SYNTHETIC-PRIVATE-TICKET",
            ["warehouse", "reverse"],
            conflicts,
            clear,
            trace_file=trace_file,
        )

        events = read_trace(run_id, trace_file)

        assert len(events) == 1

        event = events[0]

        assert event["event"] == "rfp_arbitration_evaluated"
        assert event["department_count"] == 2
        assert event["trigger_ids"] == expected_triggers
        assert event["arbitration_clear"] is clear

        content = trace_file.read_text()

        assert "SYNTHETIC-PRIVATE-TICKET" not in content
        assert "SECRET-COMMERCIAL-DATA" not in content
        assert "SYNTHETIC APPROVER" not in content
