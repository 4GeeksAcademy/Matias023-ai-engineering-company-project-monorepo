"""Configuracion de autenticacion OAuth del recurso MCP.

No emite tokens ni permite deshabilitar la autenticacion.
"""

from fastmcp.server.auth import JWTVerifier, RemoteAuthProvider

from oauth_config import (
    OAuthConfig,
    SUPPORTED_SCOPES,
    load_oauth_config,
)


def create_auth_provider(
    config: OAuthConfig | None = None,
) -> RemoteAuthProvider:
    """Crear proveedor protegido mediante JWT y JWKS."""

    settings = config if config is not None else load_oauth_config()

    verifier = JWTVerifier(
        jwks_uri=settings.jwks_uri,
        issuer=settings.issuer,
        audience=settings.audience,
    )

    return RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[settings.issuer],
        base_url=settings.public_base_url,
        scopes_supported=list(SUPPORTED_SCOPES),
    )
