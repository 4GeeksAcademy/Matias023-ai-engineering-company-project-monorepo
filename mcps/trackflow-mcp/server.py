"""Herramientas MCP de TrackFlow.

El registro existe, pero no se publica ni ejecuta contra el backend
hasta disponer de OAuth y delegacion de identidad verificados.
"""

from typing import Literal

from fastmcp import FastMCP
from fastmcp.server.auth import require_scopes
from fastmcp.server.dependencies import get_access_token

from oauth_provider import create_auth_provider
from trackflow_api import TrackFlowAPI


mcp = FastMCP(
    "TrackFlow Enterprise Tools",
    auth=create_auth_provider(),
    instructions=(
        "Herramientas de incidentes y consultas de inventario "
        "de TrackFlow. Operaciones sujetas a permisos OAuth."
    ),
)

api = TrackFlowAPI()


def backend_token() -> str:
    """Exigir credenciales backend delegadas, nunca un secreto global."""
    access = get_access_token()
    if access is None:
        raise PermissionError("MCP authentication required")

    # El backend vuelve a validar firma, identidad y permisos.
    token = access.token
    if not isinstance(token, str) or not token.strip():
        raise PermissionError("Valid OAuth bearer token required")
    return token


@mcp.tool(auth=require_scopes("incidents:read"))
async def get_incident(incident_id: int) -> dict:
    """Consultar un incidente existente por su identificador."""
    return await api.get_incident(incident_id, backend_token())


@mcp.tool(auth=require_scopes("incidents:read"))
async def list_incidents() -> dict:
    """Listar incidentes del gestor TrackFlow."""
    return await api.list_incidents(backend_token())


@mcp.tool(auth=require_scopes("incidents:write"))
async def create_incident(
    title: str,
    description: str,
    category: Literal[
        "lost_parcel", "delivery_failure",
        "inventory_discrepancy", "carrier_issue",
        "returns_issue", "warehouse_incident",
        "system_failure", "client_complaint", "other",
    ],
    origin: Literal["customer", "branch", "internal"],
    branch: Literal[
        "central", "la_warehouse", "la_office",
        "zaragoza_warehouse", "zaragoza_office",
    ],
) -> dict:
    """Crear un incidente validado mediante el backend TrackFlow."""
    payload = {
        "title": title,
        "description": description,
        "category": category,
        "origin": origin,
        "branch": branch,
        "status": "open",
    }
    return await api.create_incident(payload, backend_token())


@mcp.tool(auth=require_scopes("incidents:write"))
async def update_incident_status(
    incident_id: int,
    status: Literal["open", "in_progress", "resolved", "discarded"],
) -> dict:
    """Actualizar el estado respetando las transiciones del backend."""
    return await api.update_incident_status(
        incident_id, status, backend_token()
    )


@mcp.tool(auth=require_scopes("inventory:read"))
async def list_products() -> dict:
    """Consultar productos y existencias sin modificar inventario."""
    return await api.list_products(backend_token())


@mcp.tool(auth=require_scopes("inventory:read"))
async def get_product(product_id: int) -> dict:
    """Consultar un producto y su stock calculado por TrackFlow."""
    return await api.get_product(product_id, backend_token())
