"""Evaluaciones verificables del agente TrackFlow."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "scripts/rag"))

from agent_graph import build_agent
from agent_tracing import run_traced
from generate import ABSTENTION, RAGService


class FakeRetriever:
    def __init__(self, hits):
        self.hits = hits
        self.calls = 0

    def retrieve(self, question, **kwargs):
        self.calls += 1
        assert kwargs["top_k"] == 3
        assert kwargs["threshold"] == 0.54
        return self.hits


class FakeGenerator:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def __call__(self, prompt):
        self.calls += 1
        assert "FRAGMENTOS RECUPERADOS" in prompt
        return self.answer


def evaluate(tmp_path, question, hits, answer):
    retriever = FakeRetriever(hits)
    generator = FakeGenerator(answer)
    service = RAGService(
        retriever=retriever,
        generator=generator,
    )
    trace_file = tmp_path / "eval_trace.jsonl"

    result = run_traced(
        build_agent(service),
        question,
        trace_file=trace_file,
    )

    events = [
        json.loads(line)
        for line in trace_file.read_text(
            encoding="utf-8"
        ).splitlines()
    ]

    nodes = [
        e["node"]
        for e in events
        if e["event"] == "node_completed"
    ]

    return result, nodes, retriever, generator


def test_eval_01_recuperacion_antes_de_generacion(tmp_path):
    hit = {
        "text": "SEUR: mejor cobertura en Aragón rural.",
        "source_document": "carrier-coverage",
        "source_file": "trackflow-carrier-coverage.es.md",
        "section": "Cobertura",
        "chunk_index": 1,
        "score": 0.80,
    }

    result, nodes, retriever, generator = evaluate(
        tmp_path,
        "¿Qué transportista cubre Aragón rural?",
        [hit],
        "SEUR ofrece mejor cobertura en Aragón rural [1].",
    )

    assert nodes == ["receive", "retrieve", "generate"]
    assert retriever.calls == 1
    assert generator.calls == 1
    assert result["abstained"] is False
    assert result["sources"][0]["citation"] == 1


def test_eval_02_sin_evidencia_no_genera(tmp_path):
    result, nodes, retriever, generator = evaluate(
        tmp_path,
        "¿Qué información no documentada puedes confirmar?",
        [],
        "Respuesta inventada [1].",
    )

    assert nodes == ["receive", "retrieve", "abstain"]
    assert retriever.calls == 1
    assert generator.calls == 0
    assert result["abstained"] is True
    assert result["answer"] == ABSTENTION


def test_eval_03_respuesta_anclada_a_trackflow(tmp_path):
    document = (
        ROOT
        / "docs/company-knowledge-base"
        / "trackflow-storage-pricing.es.md"
    )
    evidence = document.read_text(encoding="utf-8")

    # El criterio procede de la documentación empresarial,
    # no de una respuesta generada libremente.
    assert "Miguel Torres" in evidence
    assert "descuentos" in evidence.casefold()

    hit = {
        "text": evidence,
        "source_document": "storage-pricing",
        "source_file": document.name,
        "section": "Politica de almacenamiento",
        "chunk_index": 1,
        "score": 0.90,
    }

    result, nodes, retriever, generator = evaluate(
        tmp_path,
        "¿Quién debe aprobar descuentos de almacenamiento?",
        [hit],
        (
            "Los descuentos de almacenamiento requieren "
            "aprobación de Miguel Torres [1]."
        ),
    )

    assert nodes == ["receive", "retrieve", "generate"]
    assert retriever.calls == 1
    assert generator.calls == 1
    assert result["abstained"] is False
    assert "Miguel Torres" in result["answer"]
    assert "aprobación" in result["answer"]
    assert result["sources"][0]["source_file"] == document.name
