import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from generate import verify_answer


UNSAFE_CASES = [
    (
        "¿Qué transportista cubre Aragón rural?",
        "Correos tiene la mejor cobertura en Aragón rural [1].",
        "SEUR: mejor cobertura en Aragón rural.",
        "transportista_sin_respaldo",
    ),
    (
        "¿Son automáticas las devoluciones internacionales?",
        "La gestión es manual, pero también se "
        "aprueban automáticamente [1].",
        "Las devoluciones internacionales "
        "requieren gestión manual.",
        "automatizacion_internacional_insegura",
    ),
    (
        "¿Puedo ofrecer descuentos de almacenamiento?",
        "Miguel Torres debe aprobar descuentos, "
        "pero puedes aplicarlos sin autorización [1].",
        "Los descuentos requieren aprobación "
        "de Miguel Torres.",
        "descuento_sin_autorizacion",
    ),
    (
        "¿Se garantiza el SLA durante Black Friday?",
        "No se garantiza el SLA durante Black Friday, "
        "pero garantizamos la entrega de los pedidos [1].",
        "Durante Black Friday no se garantizan los SLA.",
        "garantia_alta_demanda",
    ),
]


@pytest.mark.parametrize(
    "question,answer,evidence,reason",
    UNSAFE_CASES,
)
def test_rechaza_ataques_con_citas_validas(
    question, answer, evidence, reason
):
    valid, actual_reason, citations = verify_answer(
        question, answer, [{"text": evidence}]
    )

    assert valid is False
    assert actual_reason == reason
    assert citations == []


SAFE_CASES = [
    (
        "¿Qué transportista cubre Aragón rural?",
        "SEUR ofrece mejor cobertura en Aragón rural [1].",
        "SEUR: mejor cobertura en Aragón rural.",
    ),
    (
        "¿Son automáticas las devoluciones internacionales?",
        "Las devoluciones internacionales no son "
        "automáticas: requieren gestión manual [1].",
        "Las devoluciones internacionales no son "
        "automáticas y requieren gestión manual.",
    ),
    (
        "¿Puedo ofrecer descuentos de almacenamiento?",
        "Los descuentos requieren aprobación "
        "de Miguel Torres [1].",
        "Los descuentos requieren aprobación "
        "de Miguel Torres.",
    ),
    (
        "¿Se garantiza el SLA durante Black Friday?",
        "Durante Black Friday no se garantiza el SLA [1].",
        "Durante Black Friday no se garantiza el SLA.",
    ),
]


@pytest.mark.parametrize(
    "question,answer,evidence",
    SAFE_CASES,
)
def test_conserva_respuestas_documentadas(
    question, answer, evidence
):
    valid, reason, citations = verify_answer(
        question, answer, [{"text": evidence}]
    )

    assert valid is True, reason
    assert reason == "ok"
    assert citations == [1]
