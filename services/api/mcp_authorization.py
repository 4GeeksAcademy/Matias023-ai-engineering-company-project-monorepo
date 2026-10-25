"""Autorización MCP por vinculación explícita de identidad.

Los registros de vinculación deben ser aprovisionados por un
administrador mediante un mecanismo confiable, nunca por el agente.
"""

from dataclasses import dataclass

from tinydb import Query


class MCPAuthorizationError(Exception):
    """Identidad sin autorización empresarial."""


@dataclass(frozen=True)
class AuthorizedMCPUser:
    user_id: int
    role: str


def authorize_mcp_identity(
    identity,
    *,
    issuer: str,
    required_scope: str,
    bindings_table,
    users_table,
) -> AuthorizedMCPUser:
    """Autorizar solo identidades explícitamente vinculadas."""

    if not issuer or not required_scope:
        raise MCPAuthorizationError("Invalid authorization context")

    if required_scope not in identity.scopes:
        raise MCPAuthorizationError("OAuth scope denied")

    if not identity.subject:
        raise MCPAuthorizationError("OAuth subject missing")

    binding = Query()
    matches = bindings_table.search(
        (binding.issuer == issuer)
        & (binding.subject == identity.subject)
    )

    # Fallar en cerrado ante una identidad ausente o duplicada.
    if len(matches) != 1:
        raise MCPAuthorizationError("Identity not uniquely linked")

    record = matches[0]
    grants = record.get("granted_scopes")

    if not isinstance(grants, list):
        raise MCPAuthorizationError("Invalid permission grants")

    if required_scope not in grants:
        raise MCPAuthorizationError("User permission denied")

    user_id = record.get("user_id")

    if type(user_id) is not int or user_id < 1:
        raise MCPAuthorizationError("Invalid linked user")

    user = users_table.get(doc_id=user_id)

    if user is None or user.get("is_active") is not True:
        raise MCPAuthorizationError("Linked user inactive or missing")

    role = user.get("role")
    if role not in ("admin", "manager", "user"):
        raise MCPAuthorizationError("Invalid user role")

    return AuthorizedMCPUser(user_id=user_id, role=role)
