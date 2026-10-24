"""Autenticación federada para operaciones MCP permitidas.

El backend verifica el JWT externo de forma independiente.
No intercambia tokens ni comparte SECRET_KEY.
"""

import os
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from database import db, users_table
from mcp_authorization import (
    MCPAuthorizationError,
    authorize_mcp_identity,
)
from mcp_identity import MCPIdentityError, validate_mcp_token


def required_scope_for_route(method: str, path: str) -> str | None:
    segments = path.strip("/").split("/")

    if segments[:1] == ["api"]:
        segments = segments[1:]

    if segments == ["incidents"]:
        return {
            "GET": "incidents:read",
            "POST": "incidents:write",
        }.get(method)

    if len(segments) == 2 and segments[0] == "incidents":
        if method == "GET" and segments[1].isdigit():
            return "incidents:read"

    if (
        len(segments) == 3
        and segments[0] == "incidents"
        and segments[1].isdigit()
        and segments[2] == "status"
        and method == "PATCH"
    ):
        return "incidents:write"

    if segments == ["inventory", "products"] and method == "GET":
        return "inventory:read"

    if (
        len(segments) == 3
        and segments[:2] == ["inventory", "products"]
        and segments[2].isdigit()
        and method == "GET"
    ):
        return "inventory:read"

    return None


def resolve_federated_user_id(
    token: str,
    *,
    method: str,
    path: str,
) -> int:
    scope = required_scope_for_route(method, path)

    if scope is None:
        raise HTTPException(403, "OAuth access not permitted on this route")

    issuer = os.environ.get("MCP_OAUTH_ISSUER", "").strip()
    audience = os.environ.get("MCP_OAUTH_AUDIENCE", "").strip()
    jwks_uri = os.environ.get("MCP_OAUTH_JWKS_URI", "").strip()

    if not all((issuer, audience, jwks_uri)):
        raise HTTPException(401, "Federated authentication not configured")

    parsed = urlparse(jwks_uri)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(401, "HTTPS JWKS endpoint required")

    try:
        response = httpx.get(
            jwks_uri, timeout=5.0, follow_redirects=False
        )
        response.raise_for_status()
        jwks = response.json()

        identity = validate_mcp_token(
            token,
            jwks=jwks,
            issuer=issuer,
            audience=audience,
            required_scope=scope,
        )

        authorization = authorize_mcp_identity(
            identity,
            issuer=issuer,
            required_scope=scope,
            bindings_table=db.table("mcp_bindings"),
            users_table=users_table,
        )
    except (httpx.HTTPError, ValueError, MCPIdentityError):
        raise HTTPException(401, "Invalid federated credentials") from None
    except MCPAuthorizationError:
        raise HTTPException(403, "Federated permission denied") from None

    # Política conservadora: escritura limitada a manager/admin.
    if scope == "incidents:write" and authorization.role not in (
        "admin", "manager"
    ):
        raise HTTPException(403, "Incident write permission denied")

    return authorization.user_id
