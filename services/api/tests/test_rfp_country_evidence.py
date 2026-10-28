
import pytest

from data.pipelines.rfp_intake.rfp_classifier import (
    _country_supported_by_evidence,
)


@pytest.mark.parametrize(
    "country,evidence",
    [
        ("Spain", ["Marca de moda española"]),
        ("España", ["Operaciones en España"]),
        ("ES", ["Cliente ubicado en España"]),
        ("United States", ["Empresa de Estados Unidos"]),
        ("USA", ["Servicios logísticos en EE. UU."]),
        ("US", ["Operaciones en United States"]),
    ],
)
def test_valid_country_aliases(country, evidence):
    assert _country_supported_by_evidence(
        country, evidence
    )


@pytest.mark.parametrize(
    "country,evidence",
    [
        ("United States", ["Cliente en España"]),
        ("Spain", ["Empresa de Estados Unidos"]),
        ("Spain", ["Cliente ubicado en Portugal"]),
        ("Mexico", ["Cliente ubicado en España"]),
    ],
)
def test_unsupported_country_is_rejected(country, evidence):
    assert not _country_supported_by_evidence(
        country, evidence
    )


def test_country_without_evidence_is_rejected():
    assert not _country_supported_by_evidence(
        "Spain", []
    )
