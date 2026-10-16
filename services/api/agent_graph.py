"""Agente de soporte TrackFlow con LangGraph."""

import sys
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

ROOT = Path(__file__).resolve().parents[2]
RAG_DIR = ROOT / "scripts" / "rag"

if str(RAG_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_DIR))

from generate import (
    RAGService,
    _unsupported_inbound_la,
    verify_answer,
)


class AgentState(TypedDict, total=False):
    question: str
    hits: list[dict]
    answer: str
    abstained: bool
    reason: str
    sources: list[dict]
    threshold: float


def build_agent(service=None, checkpointer=None):
    """Construye y compila el grafo sin duplicar el RAG."""
    service = service if service is not None else RAGService()

    def receive(state: AgentState):
        question = state.get("question")
        if not isinstance(question, str):
            return {"reason": "pregunta_invalida"}
        question = question.strip()
        if not question or len(question) > 1000:
            return {"question": question, "reason": "pregunta_invalida"}
        return {"question": question, "reason": "pendiente"}

    def after_receive(state: AgentState):
        return (
            "retrieve"
            if state["reason"] == "pendiente"
            else "invalid"
        )

    def retrieve(state: AgentState):
        hits = service.retriever.retrieve(
            state["question"],
            top_k=3,
            threshold=service.threshold,
        )
        hits = [
            hit for hit in hits
            if hit.get("text") and hit.get("source_document")
        ]
        if not hits:
            return {
                "hits": [],
                "reason": "sin_fragmentos_sobre_umbral",
            }
        if _unsupported_inbound_la(state["question"], hits):
            return {
                "hits": hits,
                "reason": "ruta_entrada_sin_respaldo",
            }
        return {"hits": hits, "reason": "contexto_disponible"}

    def after_retrieve(state: AgentState):
        return (
            "generate"
            if state["reason"] == "contexto_disponible"
            else "abstain"
        )

    def generate(state: AgentState):
        context = []
        for number, hit in enumerate(state["hits"], start=1):
            context.append(
                f"[{number}] Fuente: {hit.get('source_file')}\n"
                f"Sección: {hit.get('section')}\n"
                f"Texto: {hit['text']}"
            )

        prompt = (
            "PREGUNTA DEL USUARIO:\n"
            f"{state['question']}\n\n"
            "FRAGMENTOS RECUPERADOS:\n"
            + "\n\n".join(context)
            + "\n\nResponde solo usando estos "
            "fragmentos y cita sus números."
        )

        answer = service.generator(prompt)
        valid, reason, citations = verify_answer(
            state["question"], answer, state["hits"]
        )

        if not valid:
            return {
                **service.abstain(reason),
                "reason": reason,
            }

        sources = []
        for number in citations:
            hit = state["hits"][number - 1]
            sources.append({
                "citation": number,
                "source_document": hit["source_document"],
                "source_file": hit.get("source_file"),
                "section": hit.get("section"),
                "chunk_index": hit.get("chunk_index"),
                "score": hit.get("score"),
            })

        return {
            "answer": answer,
            "abstained": False,
            "reason": "ok",
            "sources": sources,
            "threshold": service.threshold,
        }

    def abstain(state: AgentState):
        return service.abstain(state["reason"])

    def invalid(state: AgentState):
        return {
            "answer": "La pregunta no puede estar vacía ni superar 1000 caracteres.",
            "abstained": True,
            "reason": "pregunta_invalida",
            "sources": [],
            "threshold": service.threshold,
        }

    builder = StateGraph(AgentState)
    builder.add_node("receive", receive)
    builder.add_node("retrieve", retrieve)
    builder.add_node("generate", generate)
    builder.add_node("abstain", abstain)
    builder.add_node("invalid", invalid)

    builder.add_edge(START, "receive")
    builder.add_conditional_edges(
        "receive",
        after_receive,
        {"retrieve": "retrieve", "invalid": "invalid"},
    )
    builder.add_conditional_edges(
        "retrieve",
        after_retrieve,
        {"generate": "generate", "abstain": "abstain"},
    )
    builder.add_edge("generate", END)
    builder.add_edge("abstain", END)
    builder.add_edge("invalid", END)

    return builder.compile(
        checkpointer=(
            checkpointer
            if checkpointer is not None
            else InMemorySaver()
        )
    )
