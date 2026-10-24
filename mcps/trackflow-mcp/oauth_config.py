"""Configuracion OAuth del servidor MCP TrackFlow.

No proporciona tokens ni inicia un proveedor OAuth.
Falla de forma segura ante configuracion ausente o invalida.
"""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


SUPPORTED_SCOPES = (
    "incidents:read",
    "incidents:write",
    "inventory:read",
)


@dataclass(frozen=True)
class OAuthConfig:
    issuer: str
    audience: str
    jwks_uri: str
    public_base_url: str


def _allow_local_oidc(name: str, parsed) -> bool:
    return (
        name in ("MCP_OAUTH_ISSUER", "MCP_OAUTH_JWKS_URI")
        and os.environ.get("APP_ENV", "").lower() == "development"
        and os.environ.get("MCP_ALLOW_LOCAL_HTTP_OIDC") == "1"
        and parsed.scheme == "http"
        and parsed.hostname in ("127.0.0.1", "localhost")
    )


def _require_https_url(name: str, value: str) -> str:
    parsed = urlsplit(value)

    if (
        (parsed.scheme != "https" and not _allow_local_oidc(name, parsed))
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{name}: HTTPS URL required")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{name}: invalid port") from exc

    if port is not None and not 1 <= port <= 65535:
        raise ValueError(f"{name}: invalid port")

    return value.rstrip("/")


def load_oauth_config() -> OAuthConfig:
    """Cargar configuracion obligatoria; nunca crear valores por defecto."""
    names = (
        "MCP_OAUTH_ISSUER",
        "MCP_OAUTH_AUDIENCE",
        "MCP_OAUTH_JWKS_URI",
        "MCP_PUBLIC_BASE_URL",
    )

    values = {name: os.environ.get(name, "").strip() for name in names}

    missing = [name for name in names if not values[name]]
    if missing:
        raise RuntimeError(
            "Missing OAuth configuration: " + ", ".join(missing)
        )

    return OAuthConfig(
        issuer=_require_https_url(
            "MCP_OAUTH_ISSUER", values["MCP_OAUTH_ISSUER"]
        ),
        audience=values["MCP_OAUTH_AUDIENCE"],
        jwks_uri=_require_https_url(
            "MCP_OAUTH_JWKS_URI", values["MCP_OAUTH_JWKS_URI"]
        ),
        public_base_url=_require_https_url(
            "MCP_PUBLIC_BASE_URL", values["MCP_PUBLIC_BASE_URL"]
        ),
    )
