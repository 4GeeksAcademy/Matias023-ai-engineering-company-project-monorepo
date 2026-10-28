"""Structured arbitration node for TrackFlow RFP workflows."""

from typing import Any, TypedDict

from langgraph.graph import StateGraph, START, END

from .rfp_arbitration import arbitrate


class ArbitrationState(TypedDict):
    client_country: str
    sections: dict[str, dict[str, Any]]
    conflicts: list[dict[str, Any]]
    arbitration_clear: bool


def arbitration_node(state: ArbitrationState) -> dict:
    """Detect structured conflicts without LLM negotiation."""

    conflicts = arbitrate(
        state["client_country"],
        state["sections"],
    )

    return {
        "conflicts": conflicts,
        "arbitration_clear": len(conflicts) == 0,
    }


def build_arbitration_graph():
    """Compile a graph containing a dedicated arbitration node."""

    builder = StateGraph(ArbitrationState)
    builder.add_node("arbitration", arbitration_node)
    builder.add_edge(START, "arbitration")
    builder.add_edge("arbitration", END)

    return builder.compile()
