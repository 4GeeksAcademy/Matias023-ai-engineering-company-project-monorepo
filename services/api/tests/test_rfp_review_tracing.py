"""Metadata-only traces for RFP agent review cycles."""

import json
from pathlib import Path

import pytest

from agent_tracing import read_trace, record_rfp_review


@pytest.mark.parametrize("passed", [True, False])
def test_review_trace_records_iterations_without_sensitive_text(
    tmp_path: Path, passed: bool
):
    trace_file = tmp_path / "reviews.jsonl"

    result = {
        "review_status": (
            "evaluation_passed" if passed else "needs_human_review"
        ),
        "iterations": 2,
        "missing_information": ["PRIVATE MISSING INFORMATION"],
        "evaluation_results": {
            "history": [
                {
                    "iteration": 1,
                    "evaluations": [
                        {
                            "evaluator": "readability",
                            "passed": False,
                            "feedback": ["PRIVATE FEEDBACK"],
                        },
                    ],
                },
                {
                    "iteration": 2,
                    "evaluations": [
                        {
                            "evaluator": "compliance",
                            "passed": passed,
                            "violations": ["PRIVATE RATE"],
                        },
                    ],
                },
            ],
        },
    }

    run_id = record_rfp_review(
        "PRIVATE-TICKET-ID",
        "reverse",
        result,
        key_aspect_count=3,
        had_human_feedback=True,
        trace_file=trace_file,
    )

    events = read_trace(run_id, trace_file)

    assert len(events) == 1

    event = events[0]

    assert event["event"] == "rfp_department_review_completed"
    assert event["department"] == "reverse"
    assert event["iteration_count"] == 2
    assert len(event["iteration_summaries"]) == 2
    assert event["input_summary"]["aspect_count"] == 3
    assert event["decision"] == result["review_status"]

    serialized = trace_file.read_text()

    for secret in (
        "PRIVATE-TICKET-ID",
        "PRIVATE FEEDBACK",
        "PRIVATE RATE",
        "PRIVATE MISSING INFORMATION",
    ):
        assert secret not in serialized
