"""Pruebas de autorizacion de cambios de transportista."""

import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from generate import verify_answer


QUESTION = (
    "¿Puedo cambiar de transportista "
    "sin aprobación de Carlos Vega?"
)

EVIDENCE = [{
    "text": (
        "Las excepciones de cambio de transportista "
        "requieren aprobación de Carlos Vega."
    )
}]


@pytest.mark.parametrize(
    "answer,expected",
    [
        (
            "Puedes cambiar de transportista "
            "sin aprobación de Carlos Vega [1].",
            False,
        ),
        (
            "No necesitas autorización de Carlos Vega "
            "para cambiar de transportista [1].",
            False,
        ),
        (
            "Se permite cambiar de transportista "
            "sin autorización de Carlos Vega [1].",
            False,
        ),
        (
            "Puedes cambiar el transportista "
            "sin permiso [1].",
            False,
        ),
        (
            "No es necesaria la aprobación de Carlos Vega "
            "para cambiar de transportista [1].",
            False,
        ),
        (
            "No puedes cambiar de transportista "
            "sin aprobación de Carlos Vega [1].",
            True,
        ),
        (
            "No está permitido cambiar de transportista "
            "sin aprobación de Carlos Vega [1].",
            True,
        ),
        (
            "Las excepciones requieren aprobación "
            "de Carlos Vega [1].",
            True,
        ),
        (
            "No es posible cambiar de transportista "
            "sin aprobación de Carlos Vega [1].",
            True,
        ),
    ],
)
def test_carrier_approval_policy(answer, expected):
    valid, reason, citations = verify_answer(
        QUESTION,
        answer,
        EVIDENCE,
    )

    assert valid is expected, (
        f"Respuesta: {answer}; motivo: {reason}"
    )

    if not expected:
        assert reason == "transportista_sin_aprobacion"
        assert citations == []
