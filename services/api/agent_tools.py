"""Herramienta de consulta de incidentes reales TrackFlow.

Solo lectura. No crea ni modifica incidentes.
"""

from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from models import IncidentResponse


class TicketLookupInput(BaseModel):
    incident_id: int = Field(gt=0)


class TicketLookupResult(BaseModel):
    status: Literal[
        "ok",
        "not_found",
        "unauthorized",
        "unavailable",
        "invalid_response",
    ]
    incident: IncidentResponse | None = None


def lookup_ticket(
    request: TicketLookupInput,
    *,
    token: str,
    base_url: str = "http://127.0.0.1:8000",
    timeout_seconds: float = 5.0,
    client: httpx.Client | None = None,
) -> TicketLookupResult:
    """Consulta el GET autenticado del gestor existente."""

    if not token or not token.strip():
        return TicketLookupResult(status="unauthorized")

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds debe ser positivo")

    url = (
        base_url.rstrip("/")
        + f"/api/incidents/{request.incident_id}"
    )
    headers = {"Authorization": f"Bearer {token}"}

    own_client = client is None

    if own_client:
        client = httpx.Client(timeout=timeout_seconds)

    try:
        response = client.get(
            url,
            headers=headers,
            timeout=timeout_seconds,
        )

        if response.status_code == 404:
            return TicketLookupResult(status="not_found")

        if response.status_code in (401, 403):
            return TicketLookupResult(status="unauthorized")

        if response.status_code != 200:
            return TicketLookupResult(status="unavailable")

        try:
            incident = IncidentResponse.model_validate(
                response.json()
            )
        except (ValueError, ValidationError):
            return TicketLookupResult(
                status="invalid_response"
            )

        if incident.id != request.incident_id:
            return TicketLookupResult(
                status="invalid_response"
            )

        return TicketLookupResult(
            status="ok",
            incident=incident,
        )

    except httpx.RequestError:
        return TicketLookupResult(status="unavailable")

    finally:
        if own_client:
            client.close()
