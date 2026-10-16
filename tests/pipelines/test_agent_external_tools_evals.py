"""Evaluaciones de enrutamiento RAG / tickets TrackFlow."""

import json
from types import SimpleNamespace

from agent_graph import build_agent
from agent_tracing import run_traced
from generate import RAGService


HIT = {
    "id": "eval-1",
    "score": 0.80,
    "source_document": "carrier-coverage",
    "source_file": "trackflow-carrier-coverage.es.md",
    "section": "Cobertura",
    "chunk_index": 1,
    "text": "SEUR: mejor cobertura en Aragón rural.",
}


class Retriever:
    def __init__(self, hits):
        self.hits = hits
        self.calls = 0

    def retrieve(self, question, **kwargs):
        self.calls += 1
        return self.hits


class Generator:
    def __init__(self):
        self.calls = 0

    def __call__(self, prompt):
        self.calls += 1
        return "SEUR ofrece mejor cobertura en Aragón rural [1]."


def make_service(hits):
    retriever = Retriever(hits)
    generator = Generator()
    service = RAGService(
        retriever=retriever,
        generator=generator,
    )
    return service, retriever, generator


def trace_events(path):
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
    ]


def trace_nodes(events):
    return [
        event["node"]
        for event in events
        if event["event"] == "node_completed"
    ]


def test_eval_consulta_ticket_usa_tool_no_rag(tmp_path):
    service, retriever, generator = make_service([HIT])
    calls = []

    def ticket_tool(request, **kwargs):
        calls.append((request, kwargs))
        return SimpleNamespace(
            status="ok",
            incident=SimpleNamespace(
                id=42,
                title="Incidencia de prueba",
                status="open",
            ),
        )

    graph = build_agent(service, ticket_tool=ticket_tool)
    trace_file = tmp_path / "ticket.jsonl"
    secret = "TOKEN_PRIVADO_EVAL_123"

    result = run_traced(
        graph,
        "¿Cuál es el estado del ticket 42?",
        context={"token": secret},
        trace_file=trace_file,
    )

    events = trace_events(trace_file)
    nodes = trace_nodes(events)

    assert nodes == ["receive", "route", "ticket_lookup"]
    assert result["reason"] == "ticket_ok"
    assert result["abstained"] is False
    assert "open" in result["answer"]
    assert retriever.calls == 0
    assert generator.calls == 0
    assert len(calls) == 1
    assert calls[0][0].incident_id == 42
    assert calls[0][1]["token"] == secret
    assert calls[0][1]["timeout_seconds"] == 5.0
    assert secret not in trace_file.read_text()
    assert any(
        e.get("output_summary", {}).get("source_route")
        == "ticket"
        for e in events
    )


def test_eval_consulta_documental_usa_rag_no_tool(tmp_path):
    service, retriever, generator = make_service([HIT])

    def forbidden_tool(*args, **kwargs):
        raise AssertionError(
            "No se debe consultar tickets para esta pregunta"
        )

    graph = build_agent(service, ticket_tool=forbidden_tool)
    trace_file = tmp_path / "rag.jsonl"

    result = run_traced(
        graph,
        "¿Qué transportista cubre Aragón rural?",
        trace_file=trace_file,
    )

    events = trace_events(trace_file)
    nodes = trace_nodes(events)

    assert nodes == ["receive", "route", "retrieve", "generate"]
    assert result["abstained"] is False
    assert retriever.calls == 1
    assert generator.calls == 1
    assert len(result["sources"]) == 1
    assert any(
        e.get("output_summary", {}).get("source_route")
        == "rag"
        for e in events
    )


def test_eval_ticket_sin_jwt_no_invoca_tool(tmp_path):
    service, retriever, generator = make_service([HIT])

    def forbidden_tool(*args, **kwargs):
        raise AssertionError(
            "No consultar tickets sin autenticación"
        )

    graph = build_agent(service, ticket_tool=forbidden_tool)
    trace_file = tmp_path / "sin-token.jsonl"

    result = run_traced(
        graph,
        "Consulta el ticket 42",
        trace_file=trace_file,
    )

    assert result["abstained"] is True
    assert result["reason"] == "ticket_sin_autorizacion"
    assert retriever.calls == 0
    assert generator.calls == 0
    assert trace_nodes(trace_events(trace_file)) == [
        "receive", "route", "ticket_lookup"
    ]
