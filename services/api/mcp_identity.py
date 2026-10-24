"""Validación independiente de tokens OAuth externos para TrackFlow.

No sustituye la autenticación JWT original de TrackFlow.
No concede acceso a usuarios sin una vinculación explícita.
"""

from dataclasses import dataclass

from jose import JWTError, jwt


class MCPIdentityError(Exception):
    """Token o permisos externos rechazados."""


@dataclass(frozen=True)
class MCPIdentity:
    subject: str
    scopes: frozenset[str]


def validate_mcp_token(
    token: str,
    *,
    jwks: dict,
    issuer: str,
    audience: str,
    required_scope: str,
) -> MCPIdentity:
    """Validar firma, claims estándar y scope requerido."""

    if not token or not issuer or not audience or not required_scope:
        raise MCPIdentityError("Missing authentication parameters")

    if not isinstance(jwks, dict) or not jwks.get("keys"):
        raise MCPIdentityError("Missing trusted signing keys")

    try:
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
            options={"require_exp": True, "require_iat": True},
        )
    except (JWTError, ValueError, TypeError) as exc:
        raise MCPIdentityError("Invalid OAuth token") from exc

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise MCPIdentityError("Missing OAuth subject")

    raw_scopes = claims.get("scope", "")
    if not isinstance(raw_scopes, str):
        raise MCPIdentityError("Invalid OAuth scopes")

    scopes = frozenset(raw_scopes.split())

    if required_scope not in scopes:
        raise MCPIdentityError("Insufficient OAuth scope")

    return MCPIdentity(subject=subject, scopes=scopes)
