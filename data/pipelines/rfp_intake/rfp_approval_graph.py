"""Human approval graph for TrackFlow RFP department sections."""

from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt


APPROVERS = {
    "warehouse": "Ana Whitfield",
    "lastmile": "Carlos Vega",
    "reverse": "Sofía Ramos",
}

DECISIONS = {"approve", "request_changes"}


class ApprovalState(TypedDict):
    ticket_id: str
    department_id: str
    draft_content: str
    decision: str | None
    feedback: str | None
    approver: str | None


def approval_thread_id(
    ticket_id: str,
    department_id: str,
    revision: int = 0,
) -> str:
    """Identify one department and one immutable approval revision."""
    if not ticket_id:
        raise ValueError("ticket_id is required")
    if department_id not in APPROVERS:
        raise ValueError("Unknown department")
    if type(revision) is not int or revision < 0:
        raise ValueError("Invalid approval revision")

    base = f"rfp-approval:{ticket_id}:{department_id}"
    return base if revision == 0 else f"{base}:revision:{revision}"


def human_approval(state: ApprovalState) -> dict:
    """Pause until the responsible department reviewer decides."""
    department_id = state["department_id"]
    if department_id not in APPROVERS:
        raise ValueError("Unknown department")

    response = interrupt({
        "ticket_id": state["ticket_id"],
        "department_id": department_id,
        "approver": APPROVERS[department_id],
        "draft_content": state["draft_content"],
        "actions": sorted(DECISIONS),
    })

    if not isinstance(response, dict):
        raise ValueError("Approval decision must be an object")

    decision = response.get("decision")
    if decision not in DECISIONS:
        raise ValueError("Invalid approval decision")

    if response.get("approver") != APPROVERS[department_id]:
        raise ValueError("Incorrect department approver")

    feedback = response.get("feedback")
    if decision == "request_changes" and (
        not isinstance(feedback, str) or not feedback.strip()
    ):
        raise ValueError("Feedback required for requested changes")

    return {
        "decision": decision,
        "feedback": feedback,
        "approver": APPROVERS[department_id],
    }


def build_approval_graph(checkpointer):
    """Compile an approval graph with a persistent checkpointer."""
    if checkpointer is None:
        raise ValueError("A checkpointer is required")

    builder = StateGraph(ApprovalState)
    builder.add_node("human_approval", human_approval)
    builder.add_edge(START, "human_approval")
    builder.add_edge("human_approval", END)

    return builder.compile(checkpointer=checkpointer)
