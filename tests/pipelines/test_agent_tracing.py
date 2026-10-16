"""Verifica trazas persistentes sin datos de consulta."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "scripts/rag"))

from agent_graph import build_agent
from agent_tracing import read_trace, run_traced
from generate import ABSTENTION, RAGService


class FakeRetriever:
    def retrieve(self, question, **kwargs):
        return []


class FakeGenerator:
    def __call__(self, prompt):
        raise AssertionError("No debe llamarse Gemini")


def test_traza_persistente_y_consultable(tmp_path):
    trace_file = tmp_path / "traces.jsonl"

    service = RAGService(
        retriever=FakeRetriever(),
        generator=FakeGenerator(),
    )

    graph = build_agent(service)

    secret_question = "Consulta privada de ejemplo"

    result = run_traced(
        graph,
        secret_question,
        trace_file=trace_file,
    )

    assert result["answer"] == ABSTENTION

    events = [
        json.loads(line)
        for line in trace_file.read_text().splitlines()
    ]

    assert [e["event"] for e in events] == [
        "run_started",
        "node_completed",
        "node_completed",
        "node_completed",
        "run_completed",
    ]

    nodes = [
        e["node"]
        for e in events
        if e["event"] == "node_completed"
    ]

    assert nodes == ["receive", "retrieve", "abstain"]

    run_id = events[0]["run_id"]
    assert len(read_trace(run_id, trace_file)) == 5

    content = trace_file.read_text()
    assert secret_question not in content
    assert ABSTENTION not in content

    assert events[-1]["abstained"] is True
    assert events[-1]["nodes_executed"] == 3


def test_traza_pregunta_invalida(tmp_path):
    trace_file = tmp_path / "invalid.jsonl"

    service = RAGService(
        retriever=FakeRetriever(),
        generator=FakeGenerator(),
    )

    result = run_traced(
        build_agent(service),
        "   ",
        trace_file=trace_file,
    )

    assert result["reason"] == "pregunta_invalida"

    events = [
        json.loads(line)
        for line in trace_file.read_text().splitlines()
    ]

    nodes = [
        e["node"]
        for e in events
        if e["event"] == "node_completed"
    ]

    assert nodes == ["receive", "invalid"]



def test_trace_resume_resultados_sin_contenido_sensible(tmp_path):
    """La traza resume salidas sin exponer contenido privado."""
    import json
    from types import SimpleNamespace

    from agent_tracing import run_traced

    secret_question = "PREGUNTA_PRIVADA_123"
    secret_document = "DOCUMENTO_PRIVADO_456"
    secret_answer = "RESPUESTA_PRIVADA_789"

    class FakeGraph:
        def stream(self, values, config, stream_mode):
            assert stream_mode == "updates"
            yield {
                "receive": {
                    "question": values["question"],
                    "reason": "pendiente",
                }
            }
            yield {
                "retrieve": {
                    "hits": [{"text": secret_document}],
                    "reason": "contexto_disponible",
                }
            }
            yield {
                "generate": {
                    "answer": secret_answer,
                    "sources": [{"citation": 1}],
                    "abstained": False,
                    "reason": "ok",
                }
            }

        def get_state(self, config):
            return SimpleNamespace(values={
                "answer": secret_answer,
                "sources": [{"citation": 1}],
                "abstained": False,
                "reason": "ok",
            })

    trace = tmp_path / "trace.jsonl"

    result = run_traced(
        FakeGraph(),
        secret_question,
        trace_file=trace,
    )

    assert result["reason"] == "ok"

    raw = trace.read_text(encoding="utf-8")
    assert secret_question not in raw
    assert secret_document not in raw
    assert secret_answer not in raw

    events = [json.loads(line) for line in raw.splitlines()]
    nodes = [
        event for event in events
        if event["event"] == "node_completed"
    ]

    assert [item["node"] for item in nodes] == [
        "receive", "retrieve", "generate"
    ]

    assert nodes[0]["output_summary"]["question_accepted"] is True
    assert nodes[1]["output_summary"]["hit_count"] == 1
    assert nodes[2]["output_summary"]["source_count"] == 1
    assert nodes[2]["output_summary"]["answer_length"] == len(
        secret_answer
    )
    assert nodes[2]["output_summary"]["abstained"] is False
