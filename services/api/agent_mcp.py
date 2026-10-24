"""Adaptador LangGraph -> servidor MCP TrackFlow.

Requiere un token OAuth válido para el servidor MCP.
No genera, transforma ni intercambia credenciales.
"""

import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from agent_tools import TicketLookupInput, TicketLookupResult
from models import IncidentResponse


async def _fetch_incident(incident_id: int, token: str) -> dict:
    url = os.environ.get("TRACKFLOW_MCP_URL", "").strip()
    if not url or not url.startswith("https://"):
        raise ValueError("TRACKFLOW_MCP_URL must use HTTPS")

    async with streamable_http_client(
        url,
        headers={"Authorization": f"Bearer {token}"},
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_incident",
                arguments={"incident_id": incident_id},
            )

            if result.isError:
                return {"ok": False, "reason": "unavailable"}

            data = result.structuredContent
            if data is None:
                if not result.content:
                    return {"ok": False, "reason": "invalid_response"}
                text = getattr(result.content[0], "text", None)
                if not isinstance(text, str):
                    return {"ok": False, "reason": "invalid_response"}
                data = json.loads(text)

            if not isinstance(data, dict):
                return {"ok": False, "reason": "invalid_response"}

            return data


def lookup_ticket_mcp(
    request: TicketLookupInput,
    *,
    token: str,
    **_kwargs,
) -> TicketLookupResult:
    """Consultar mediante MCP, sin enviar un JWT interno de TrackFlow."""

    if not token or not token.strip():
        return TicketLookupResult(status="unauthorized")

    try:
        data = asyncio.run(_fetch_incident(request.incident_id, token))
    except (ValueError, RuntimeError):
        return TicketLookupResult(status="unavailable")
    except Exception:
        # No exponer al usuario datos internos de transporte o autenticación.
        return TicketLookupResult(status="unavailable")

    if data.get("ok") is not True:
        reason = data.get("reason")
        status = {
            "unauthorized": "unauthorized",
            "not_found": "not_found",
            "invalid_response": "invalid_response",
        }.get(reason, "unavailable")
        return TicketLookupResult(status=status)

    try:
        incident = IncidentResponse.model_validate(data.get("data"))
    except (ValueError, TypeError):
        return TicketLookupResult(status="invalid_response")

    if incident.id != request.incident_id:
        return TicketLookupResult(status="invalid_response")

    return TicketLookupResult(status="ok", incident=incident)
