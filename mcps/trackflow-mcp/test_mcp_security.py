"""Pruebas locales de protección HTTP del recurso MCP."""

import asyncio
import importlib
from unittest.mock import patch

import httpx
import pytest


SETTINGS = {
    "MCP_OAUTH_ISSUER": "https://issuer.example.org",
    "MCP_OAUTH_AUDIENCE": "trackflow-mcp",
    "MCP_OAUTH_JWKS_URI": "https://issuer.example.org/jwks",
    "MCP_PUBLIC_BASE_URL": "https://mcp.example.org",
}

RESOURCE_PATH = "/.well-known/oauth-protected-resource/mcp"


@pytest.fixture
def app():
    with patch.dict("os.environ", SETTINGS):
        server = importlib.import_module("server")
        return server.mcp.http_app(
            transport="streamable-http",
            stateless_http=True,
        )


def request(app, method, path, **kwargs):
    async def execute():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://mcp.example.org",
        ) as client:
            return await client.request(
                method, path, **kwargs
            )

    return asyncio.run(execute())


def test_anonymous_access_denied(app):
    response = request(
        app,
        "POST",
        "/mcp",
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "security-test",
                    "version": "1.0",
                },
            },
        },
    )

    assert response.status_code == 401
    assert RESOURCE_PATH in response.headers.get(
        "www-authenticate", ""
    )


def test_resource_metadata(app):
    response = request(app, "GET", RESOURCE_PATH)

    assert response.status_code == 200
    metadata = response.json()

    assert metadata["resource"] == (
        "https://mcp.example.org/mcp"
    )

    servers = {
        value.rstrip("/")
        for value in metadata["authorization_servers"]
    }
    assert "https://issuer.example.org" in servers


def test_scopes_published(app):
    response = request(app, "GET", RESOURCE_PATH)

    assert response.status_code == 200

    scopes = set(response.json()["scopes_supported"])

    assert scopes == {
        "incidents:read",
        "incidents:write",
        "inventory:read",
    }


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Bearer invalid-token",
        "Bearer ",
    ],
)
def test_invalid_bearer_tokens(app, authorization):
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if authorization is not None:
        headers["Authorization"] = authorization

    response = request(
        app,
        "POST",
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "security-test",
                    "version": "1.0",
                },
            },
        },
    )

    assert response.status_code == 401
