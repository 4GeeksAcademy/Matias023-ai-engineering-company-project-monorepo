import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/rag"))

from generate import (
    ABSTENTION,
    RAGService,
    GeminiGenerator,
    verify_answer,
)


HIT = {
    "id": "sample",
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
        self.calls = []

    def retrieve(self, question, **kwargs):
        self.calls.append(kwargs)
        return self.hits


class FakeGenerator:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def __call__(self, prompt):
        self.calls += 1
        assert "FRAGMENTOS RECUPERADOS" in prompt
        return self.answer


def test_respuesta_con_cita_y_fuente():
    retriever = FakeRetriever([HIT])

    generator = FakeGenerator(
        "SEUR ofrece mejor cobertura "
        "en Aragón rural [1]."
    )

    result = RAGService(
        retriever=retriever,
        generator=generator,
    ).query("¿Qué transportista cubre Aragón rural?")

    assert result["abstained"] is False
    assert len(result["sources"]) == 1
    assert result["sources"][0]["chunk_index"] == 1
    assert retriever.calls[0]["threshold"] == 0.54


def test_sin_evidencia_no_llama_al_llm():
    generator = FakeGenerator("Respuesta inventada")

    result = RAGService(
        retriever=FakeRetriever([]),
        generator=generator,
    ).query("Pregunta sin documentacion")

    assert result["abstained"] is True
    assert result["answer"] == ABSTENTION
    assert generator.calls == 0


@pytest.mark.parametrize("answer", [
    "SEUR cubre Aragón rural.",
    "SEUR cubre Aragón rural [99].",
    "Ofrecemos entrega garantizada en 999 días [1].",
])
def test_rechaza_respuestas_no_fundamentadas(answer):
    result = RAGService(
        retriever=FakeRetriever([HIT]),
        generator=FakeGenerator(answer),
    ).query("¿Qué cobertura ofrece SEUR?")

    assert result["abstained"] is True


def test_descuentos_exigen_aprobacion():
    valid, reason, _ = verify_answer(
        "¿Puedo ofrecer un descuento de almacenamiento?",
        "Sí, puedes ofrecer un descuento [1].",
        [{
            "text": (
                "Los descuentos requieren "
                "aprobación de Miguel Torres."
            )
        }],
    )

    assert valid is False
    assert reason == "descuento_sin_aprobacion"


def test_devolucion_internacional_manual():
    valid, reason, _ = verify_answer(
        "¿Son automáticas las devoluciones internacionales?",
        "Las devoluciones internacionales son automáticas [1].",
        [{
            "text": (
                "Las devoluciones internacionales "
                "requieren gestión manual."
            )
        }],
    )

    assert valid is False
    assert reason == "devolucion_internacional"


def test_black_friday_sin_promesa():
    valid, reason, _ = verify_answer(
        "¿Se garantiza el SLA en Black Friday?",
        "El SLA se garantiza durante Black Friday [1].",
        [{
            "text": (
                "En Black Friday no se garantiza el SLA."
            )
        }],
    )

    assert valid is False
    assert reason == "promesa_sla_no_verificada"


def test_pregunta_vacia():
    service = RAGService(
        retriever=FakeRetriever([]),
        generator=FakeGenerator(""),
    )

    with pytest.raises(ValueError):
        service.query("   ")


def test_adaptador_gemini_con_mock():
    class FakeModels:
        def generate_content(self, **kwargs):
            assert kwargs["model"] == (
                "gemini-3.5-flash-lite"
            )

            return SimpleNamespace(
                text="Respuesta fundamentada [1]."
            )

    fake_client = SimpleNamespace(
        models=FakeModels()
    )

    generator = GeminiGenerator(client=fake_client)

    assert "[1]" in generator("Pregunta y contexto")
