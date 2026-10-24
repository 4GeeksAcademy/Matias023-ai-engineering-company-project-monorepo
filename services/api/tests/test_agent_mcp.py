"""Pruebas aisladas del adaptador LangGraph-MCP."""

import pytest

import agent_mcp
from agent_tools import TicketLookupInput
from models import IncidentResponse


def use_response(monkeypatch, response):
    async def fake_fetch(incident_id, token):
        assert incident_id == 7
        assert token == "oauth-test-token"
        return response

    monkeypatch.setattr(agent_mcp, "_fetch_incident", fake_fetch)


def lookup(token="oauth-test-token"):
    return agent_mcp.lookup_ticket_mcp(
        TicketLookupInput(incident_id=7),
        token=token,
    )


def test_missing_token_rejected():
    assert lookup(token="").status == "unauthorized"


def test_mcp_not_found(monkeypatch):
    use_response(
        monkeypatch, {"ok": False, "reason": "not_found"}
    )
    assert lookup().status == "not_found"


def test_mcp_denied(monkeypatch):
    use_response(
        monkeypatch, {"ok": False, "reason": "unauthorized"}
    )
    assert lookup().status == "unauthorized"


def test_mcp_backend_unavailable(monkeypatch):
    use_response(
        monkeypatch, {"ok": False, "reason": "backend_unavailable"}
    )
    assert lookup().status == "unavailable"


def test_mcp_success(monkeypatch):
    incident = IncidentResponse(
        id=7,
        title="Incidente de prueba",
        description="Descripción de prueba",
        category="lost_parcel",
        status="open",
        origin="customer",
        branch="la_office",
        created_at="2026-10-24T12:00:00+00:00",
        updated_at="2026-10-24T12:00:00+00:00",
    )
    use_response(
        monkeypatch,
        {"ok": True, "data": incident.model_dump()},
    )
    result = lookup()
    assert result.status == "ok"
    assert result.incident.id == 7


def test_mcp_wrong_incident_id(monkeypatch):
    incident = IncidentResponse(
        id=99,
        title="Incidente de prueba",
        description="Descripción de prueba",
        category="lost_parcel",
        status="open",
        origin="customer",
        branch="la_office",
        created_at="2026-10-24T12:00:00+00:00",
        updated_at="2026-10-24T12:00:00+00:00",
    )
    use_response(
        monkeypatch,
        {"ok": True, "data": incident.model_dump()},
    )
    assert lookup().status == "invalid_response"


def test_mcp_transport_exception(monkeypatch):
    async def broken_fetch(incident_id, token):
        raise ConnectionError("internal network details")

    monkeypatch.setattr(
        agent_mcp, "_fetch_incident", broken_fetch
    )
    assert lookup().status == "unavailable"
