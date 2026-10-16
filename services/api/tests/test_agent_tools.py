"""Pruebas aisladas de la tool de incidentes reales."""

from datetime import datetime, timezone

import httpx
import pytest

from agent_tools import (
    TicketLookupInput,
    lookup_ticket,
)


def incident_payload(incident_id=7):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": incident_id,
        "title": "Incidencia de entrega",
        "description": "Entrega pendiente",
        "category": "delivery_failure",
        "origin": "customer",
        "branch": "central",
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }


def lookup_with_handler(handler, incident_id=7):
    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        return lookup_ticket(
            TicketLookupInput(incident_id=incident_id),
            token="jwt-de-prueba",
            base_url="http://testserver",
            timeout_seconds=5.0,
            client=client,
        )


def test_ticket_real_contract_get_autenticado():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/api/incidents/7"
        assert request.headers["Authorization"] == (
            "Bearer jwt-de-prueba"
        )
        return httpx.Response(
            200,
            json=incident_payload(),
        )

    result = lookup_with_handler(handler)
    assert result.status == "ok"
    assert result.incident.id == 7
    assert result.incident.status == "open"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (404, "not_found"),
        (401, "unauthorized"),
        (403, "unauthorized"),
        (500, "unavailable"),
    ],
)
def test_ticket_errores_http(code, expected):
    result = lookup_with_handler(
        lambda request: httpx.Response(code)
    )
    assert result.status == expected
    assert result.incident is None


def test_ticket_timeout():
    def handler(request):
        raise httpx.ReadTimeout("timeout simulado")

    result = lookup_with_handler(handler)
    assert result.status == "unavailable"
    assert result.incident is None


def test_ticket_respuesta_invalida():
    result = lookup_with_handler(
        lambda request: httpx.Response(
            200,
            json={"id": 7, "status": "open"},
        )
    )
    assert result.status == "invalid_response"


def test_ticket_id_incorrecto():
    result = lookup_with_handler(
        lambda request: httpx.Response(
            200,
            json=incident_payload(99),
        )
    )
    assert result.status == "invalid_response"


def test_ticket_sin_token_no_consulta():
    result = lookup_ticket(
        TicketLookupInput(incident_id=7),
        token="",
    )
    assert result.status == "unauthorized"


def test_ticket_id_invalido():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TicketLookupInput(incident_id=0)
