"""Pruebas iniciales del agente LangGraph."""

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "api"))
sys.path.insert(0, str(ROOT / "scripts" / "rag"))

from agent_graph import build_agent
from generate import ABSTENTION, RAGService


HIT = {
    "id": "test",
    "score": 0.80,
    "source_document": "carrier-coverage",
    "source_file": "trackflow-carrier-coverage.es.md",
    "section": "Cobertura",
    "chunk_index": 1,
    "text": "SEUR: mejor cobertura en Aragón rural.",
}


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


def run(question, hits, answer):
    retriever = FakeRetriever(hits)
    generator = FakeGenerator(answer)
    service = RAGService(
        retriever=retriever,
        generator=generator,
    )
    graph = build_agent(service)
    config = {"configurable": {"thread_id": str(uuid4())}}
    result = graph.invoke({"question": question}, config)
    return result, retriever, generator, graph, config


def test_respuesta_con_evidencia():
    result, retriever, generator, graph, config = run(
        "¿Qué transportista cubre Aragón rural?",
        [HIT],
        "SEUR ofrece mejor cobertura en Aragón rural [1].",
    )
    assert result["abstained"] is False
    assert len(result["sources"]) == 1
    assert retriever.calls == 1
    assert generator.calls == 1
    assert graph.get_state(config).values["reason"] == "ok"


def test_sin_evidencia_abstiene():
    result, retriever, generator, _, _ = run(
        "Pregunta sin respaldo",
        [],
        "Respuesta inventada",
    )
    assert result["abstained"] is True
    assert result["answer"] == ABSTENTION
    assert retriever.calls == 1
    assert generator.calls == 0


def test_pregunta_vacia_no_recupera():
    result, retriever, generator, _, _ = run(
        "   ",
        [HIT],
        "Respuesta inventada",
    )
    assert result["reason"] == "pregunta_invalida"
    assert retriever.calls == 0
    assert generator.calls == 0


def test_respuesta_sin_cita_se_rechaza():
    result, retriever, generator, _, _ = run(
        "¿Qué cobertura ofrece SEUR?",
        [HIT],
        "SEUR tiene cobertura mundial.",
    )
    assert result["abstained"] is True
    assert result["reason"] == "citas_invalidas"
    assert retriever.calls == 1
    assert generator.calls == 1


def test_ruta_invertida_se_bloquea():
    hit = {
        **HIT,
        "text": (
            "DHL: única opción con cobertura confiable "
            "para envíos internacionales desde Los Ángeles."
        ),
    }
    result, retriever, generator, _, _ = run(
        "¿Qué transportista realiza envíos hacia Los Ángeles?",
        [hit],
        "DHL cubre esa ruta [1].",
    )
    assert result["reason"] == "ruta_entrada_sin_respaldo"
    assert retriever.calls == 1
    assert generator.calls == 0
