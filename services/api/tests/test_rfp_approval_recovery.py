"""Recovery tests for human RFP approvals without a live database."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from langgraph.checkpoint.sqlite import SqliteSaver

import rfp_approval_service as service
from data.pipelines.rfp_intake.rfp_approval_graph import (
    build_approval_graph,
)


@pytest.mark.parametrize(
    "decision,feedback,expected_status",
    [
        ("approve", None, "approved"),
        (
            "request_changes",
            "Correct the department proposal",
            "request_changes",
        ),
    ],
)
def test_recovery_after_commit_failure(
    tmp_path,
    decision,
    feedback,
    expected_status,
):
    """A completed checkpoint can recover a failed SQL commit."""

    ticket_id = "TEST-RFP-RECOVERY"
    department_id = "warehouse"
    draft = "Synthetic RFP draft"

    ticket = SimpleNamespace(
        status="esperando_aprobación",
        updated_at=None,
    )

    section = SimpleNamespace(
        draft_content=draft,
        approval_status="pending",
        approver=None,
        approved_at=None,
        evaluation_results={"approval_revision": 0},
    )

    fail_commit = [True]

    class FakeSession:
        def __init__(self, engine):
            self.engine = engine

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @contextmanager
        def begin(self):
            old_ticket = deepcopy(ticket.__dict__)
            old_section = deepcopy(section.__dict__)

            try:
                yield

                if fail_commit[0]:
                    fail_commit[0] = False
                    raise RuntimeError("INDUCED_COMMIT_FAILURE")

            except Exception:
                ticket.__dict__.clear()
                ticket.__dict__.update(old_ticket)

                section.__dict__.clear()
                section.__dict__.update(old_section)
                raise

        def add(self, obj):
            pass

    def load_section(session, requested_ticket, requested_department):
        assert requested_ticket == ticket_id
        assert requested_department == department_id
        return ticket, section

    db = Path(tmp_path) / "approval.sqlite"
    config = service._config(ticket_id, department_id, section)

    with SqliteSaver.from_conn_string(str(db)) as saver:
        graph = build_approval_graph(saver)

        result = graph.invoke(
            {
                "ticket_id": ticket_id,
                "department_id": department_id,
                "draft_content": draft,
                "decision": None,
                "feedback": None,
                "approver": None,
            },
            config,
        )

        assert result.get("__interrupt__")

    fake_engine = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql")
    )

    with (
        patch.object(service, "get_engine", return_value=fake_engine),
        patch.object(service, "Session", FakeSession),
        patch.object(service, "_load_active_section", load_section),
        patch.object(service, "_checkpoint_path", return_value=db),
    ):
        # First attempt: checkpoint completes, SQL commit fails.
        with pytest.raises(
            RuntimeError,
            match="INDUCED_COMMIT_FAILURE",
        ):
            service.decide_approval(
                ticket_id,
                department_id,
                decision,
                feedback,
            )

        assert section.approval_status == "pending"

        with SqliteSaver.from_conn_string(str(db)) as saver:
            snapshot = build_approval_graph(saver).get_state(config)

            assert not snapshot.next
            assert snapshot.values["decision"] == decision

        # Recovery must reject a contradictory decision.
        conflicting = (
            "request_changes"
            if decision == "approve"
            else "approve"
        )

        conflicting_feedback = (
            "Conflicting request"
            if conflicting == "request_changes"
            else None
        )

        with pytest.raises(HTTPException) as exc:
            service.decide_approval(
                ticket_id,
                department_id,
                conflicting,
                conflicting_feedback,
            )

        assert exc.value.status_code == 409
        assert section.approval_status == "pending"

        # Recover the original completed decision.
        result = service.decide_approval(
            ticket_id,
            department_id,
            decision,
            feedback,
        )

        assert result["approval_status"] == expected_status
        assert section.approval_status == expected_status
        assert section.evaluation_results["human_decision"] == decision

        if decision == "request_changes":
            assert (
                section.evaluation_results["human_feedback"]
                == feedback
            )
            assert result["requires_regeneration"] is True
        else:
            assert result["requires_regeneration"] is False

        # The same approval must not be applied twice.
        with pytest.raises(HTTPException) as exc:
            service.decide_approval(
                ticket_id,
                department_id,
                decision,
                feedback,
            )

        assert exc.value.status_code == 409


def test_checkpoint_rejects_changed_draft(tmp_path):
    """A checkpoint must not approve a different draft."""

    ticket_id = "TEST-RFP-DRAFT"
    department_id = "warehouse"

    section = SimpleNamespace(
        draft_content="Original draft",
        approval_status="pending",
        evaluation_results={"approval_revision": 0},
    )

    ticket = SimpleNamespace(
        status="esperando_aprobación",
    )

    db = Path(tmp_path) / "approval.sqlite"
    config = service._config(ticket_id, department_id, section)

    with SqliteSaver.from_conn_string(str(db)) as saver:
        graph = build_approval_graph(saver)

        result = graph.invoke(
            {
                "ticket_id": ticket_id,
                "department_id": department_id,
                "draft_content": "Original draft",
                "decision": None,
                "feedback": None,
                "approver": None,
            },
            config,
        )

        assert result.get("__interrupt__")

    section.draft_content = "Modified draft"

    fake_engine = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql")
    )

    class FakeSession:
        def __init__(self, engine):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @contextmanager
        def begin(self):
            yield

    with (
        patch.object(service, "get_engine", return_value=fake_engine),
        patch.object(service, "Session", FakeSession),
        patch.object(
            service,
            "_load_active_section",
            return_value=(ticket, section),
        ),
        patch.object(service, "_checkpoint_path", return_value=db),
    ):
        with pytest.raises(HTTPException) as exc:
            service.decide_approval(
                ticket_id,
                department_id,
                "approve",
                None,
            )

        assert exc.value.status_code == 409
        assert section.approval_status == "pending"
