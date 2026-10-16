import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from generate import RAGService, verify_answer


OUTBOUND = (
    "DHL: única opción con cobertura confiable "
    "para envíos internacionales desde Los Ángeles."
)

INBOUND = (
    "DHL ofrece envíos internacionales "
    "hacia Los Ángeles."
)

INBOUND_EXCLUSIVE = (
    "DHL es la única empresa con cobertura "
    "para envíos internacionales hacia Los Ángeles."
)


def make_hit(text):
    return {
        "text": text,
        "source_document": "carrier-coverage",
        "source_file": (
            "trackflow-carrier-coverage.es.md"
        ),
        "section": "Cobertura de Transportistas",
        "chunk_index": 1,
        "score": 0.60,
    }


class FakeRetriever:
    def __init__(self, hits):
        self.hits = hits

    def retrieve(self, question, top_k, threshold):
        return self.hits


class FakeGenerator:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def __call__(self, prompt):
        self.calls += 1
        return self.answer


def run_query(question, evidence, answer):
    generator = FakeGenerator(answer)

    service = RAGService(
        retriever=FakeRetriever(
            [make_hit(evidence)]
        ),
        generator=generator,
    )

    return service.query(question), generator.calls


@pytest.mark.parametrize(
    "question",
    [
        (
            "¿Qué empresa ofrece cobertura exclusiva "
            "para envíos hacia Los Ángeles?"
        ),
        (
            "¿Cuál es el transportista indicado "
            "para un envío internacional a Los Ángeles?"
        ),
    ],
)
def test_bloquea_ruta_de_entrada_no_documentada(
    question,
):
    result, calls = run_query(
        question,
        OUTBOUND,
        "DHL cubre esa ruta [1].",
    )

    assert result["abstained"] is True
    assert result["reason"] == (
        "ruta_entrada_sin_respaldo"
    )
    assert calls == 0


def test_permite_ruta_desde_los_angeles():
    result, calls = run_query(
        (
            "¿Qué transportista ofrece cobertura "
            "internacional desde Los Ángeles?"
        ),
        OUTBOUND,
        "DHL ofrece esa cobertura [1].",
    )

    assert result["abstained"] is False
    assert calls == 1


def test_permite_entrada_documentada():
    result, calls = run_query(
        (
            "¿Qué transportista realiza envíos "
            "internacionales hacia Los Ángeles?"
        ),
        INBOUND,
        "DHL realiza esos envíos [1].",
    )

    assert result["abstained"] is False
    assert calls == 1


def test_exclusividad_requiere_respaldo():
    result, calls = run_query(
        (
            "¿Qué empresa tiene cobertura exclusiva "
            "para envíos hacia Los Ángeles?"
        ),
        INBOUND,
        "DHL tiene cobertura exclusiva [1].",
    )

    assert result["abstained"] is True
    assert calls == 0


def test_exclusividad_documentada():
    result, calls = run_query(
        (
            "¿Qué empresa tiene cobertura exclusiva "
            "para envíos hacia Los Ángeles?"
        ),
        INBOUND_EXCLUSIVE,
        "DHL es la única empresa [1].",
    )

    assert result["abstained"] is False
    assert calls == 1


def test_no_bloquea_consulta_general():
    result, calls = run_query(
        (
            "¿Qué transportistas operan "
            "en Los Ángeles?"
        ),
        OUTBOUND,
        "DHL es un operador mencionado [1].",
    )

    assert result["abstained"] is False
    assert calls == 1


def test_cita_no_respalda_ruta_inventada():
    valid, reason, citations = verify_answer(
        (
            "¿Qué empresa ofrece envíos "
            "exclusivos hacia Los Ángeles?"
        ),
        "DHL cubre esa ruta en exclusiva [1].",
        [make_hit(OUTBOUND)],
    )

    assert valid is False
    assert reason == "ruta_entrada_sin_respaldo"
    assert citations == []
