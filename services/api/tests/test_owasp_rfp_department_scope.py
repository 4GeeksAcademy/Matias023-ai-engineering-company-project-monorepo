"""OWASP A01: alcance departamental sobre tickets RFP."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from rfp_approval_service import _load_active_section


class FakeResult:
    def __init__(self, value):
        self.value = value

    def one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, ticket, metadata, section):
        self.values = [ticket, metadata, section]
        self.calls = 0

    def exec(self, query):
        index = self.calls
        self.calls += 1

        if index >= len(self.values):
            raise AssertionError("Unexpected database query")

        return FakeResult(self.values[index])


def ticket():
    return SimpleNamespace(
        ticket_id="rfp-sintetico-001",
        status="esperando_aprobación",
    )


def section():
    return SimpleNamespace(
        department_id="warehouse",
        draft_content="Borrador sintético",
    )


def test_department_not_assigned_to_ticket_is_rejected():
    session = FakeSession(
        ticket(),
        SimpleNamespace(departments_needed=["lastmile"]),
        section(),
    )

    with pytest.raises(HTTPException) as exc:
        _load_active_section(
            session,
            "rfp-sintetico-001",
            "warehouse",
        )

    assert exc.value.status_code == 404
    assert session.calls == 2


def test_missing_ticket_is_rejected():
    session = FakeSession(None, None, None)

    with pytest.raises(HTTPException) as exc:
        _load_active_section(
            session,
            "rfp-inexistente",
            "warehouse",
        )

    assert exc.value.status_code == 404
    assert session.calls == 1


def test_missing_department_section_is_rejected():
    session = FakeSession(
        ticket(),
        SimpleNamespace(departments_needed=["warehouse"]),
        None,
    )

    with pytest.raises(HTTPException) as exc:
        _load_active_section(
            session,
            "rfp-sintetico-001",
            "warehouse",
        )

    assert exc.value.status_code == 409


def test_active_department_with_draft_is_accepted():
    expected_ticket = ticket()
    expected_section = section()

    session = FakeSession(
        expected_ticket,
        SimpleNamespace(departments_needed=["warehouse"]),
        expected_section,
    )

    result_ticket, result_section = _load_active_section(
        session,
        "rfp-sintetico-001",
        "warehouse",
    )

    assert result_ticket is expected_ticket
    assert result_section is expected_section
    assert session.calls == 3
