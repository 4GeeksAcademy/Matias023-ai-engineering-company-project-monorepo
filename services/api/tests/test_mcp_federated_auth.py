"""Pruebas del puente OAuth con datos aislados."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from tinydb import TinyDB

import mcp_federated_auth as bridge
from mcp_identity import MCPIdentity, MCPIdentityError


@pytest.fixture
def context(tmp_path, monkeypatch):
    database = TinyDB(tmp_path / "federated-test.json")
    users = database.table("users")
    bindings = database.table("mcp_bindings")

    user_id = users.insert({
        "email": "test@example.test",
        "role": "manager",
        "is_active": True,
    })

    bindings.insert({
        "issuer": "https://issuer.example.test",
        "subject": "keycloak-user-123",
        "user_id": user_id,
        "granted_scopes": [
            "incidents:read",
            "incidents:write",
            "inventory:read",
        ],
    })

    monkeypatch.setattr(bridge, "db", database)
    monkeypatch.setattr(bridge, "users_table", users)

    monkeypatch.setenv(
        "MCP_OAUTH_ISSUER", "https://issuer.example.test"
    )
    monkeypatch.setenv(
        "MCP_OAUTH_AUDIENCE", "trackflow-mcp"
    )
    monkeypatch.setenv(
        "MCP_OAUTH_JWKS_URI",
        "https://issuer.example.test/jwks",
    )

    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"keys": [{"kid": "test"}]},
    )
    monkeypatch.setattr(
        bridge.httpx, "get", lambda *args, **kwargs: response
    )

    def fake_validation(token, **kwargs):
        if token != "valid-test-token":
            raise MCPIdentityError("Invalid token")

        return MCPIdentity(
            subject="keycloak-user-123",
            scopes=frozenset({
                "incidents:read",
                "incidents:write",
                "inventory:read",
            }),
        )

    monkeypatch.setattr(
        bridge, "validate_mcp_token", fake_validation
    )

    yield users, bindings, user_id
    database.close()


def resolve(method, path, token="valid-test-token"):
    return bridge.resolve_federated_user_id(
        token, method=method, path=path
    )


def test_read_incident_allowed(context):
    _, _, user_id = context
    assert resolve("GET", "/api/incidents/1") == user_id


def test_write_incident_allowed_for_manager(context):
    _, _, user_id = context
    assert resolve("POST", "/api/incidents") == user_id


def test_inventory_read_allowed(context):
    _, _, user_id = context
    assert resolve("GET", "/inventory/products") == user_id


def test_unlisted_route_denied(context):
    with pytest.raises(HTTPException) as error:
        resolve("DELETE", "/users/1")
    assert error.value.status_code == 403


def test_invalid_token_denied(context):
    with pytest.raises(HTTPException) as error:
        resolve("GET", "/api/incidents", "invalid")
    assert error.value.status_code == 401


def test_unlinked_identity_denied(context):
    _, bindings, _ = context
    bindings.truncate()

    with pytest.raises(HTTPException) as error:
        resolve("GET", "/api/incidents")

    assert error.value.status_code == 403


def test_inactive_user_denied(context):
    users, _, user_id = context
    users.update({"is_active": False}, doc_ids=[user_id])

    with pytest.raises(HTTPException) as error:
        resolve("GET", "/api/incidents")

    assert error.value.status_code == 403


def test_regular_user_cannot_write(context):
    users, _, user_id = context
    users.update({"role": "user"}, doc_ids=[user_id])

    with pytest.raises(HTTPException) as error:
        resolve("POST", "/api/incidents")

    assert error.value.status_code == 403


def test_http_jwks_denied(context, monkeypatch):
    monkeypatch.setenv(
        "MCP_OAUTH_JWKS_URI",
        "http://issuer.example.test/jwks",
    )

    with pytest.raises(HTTPException) as error:
        resolve("GET", "/api/incidents")

    assert error.value.status_code == 401
