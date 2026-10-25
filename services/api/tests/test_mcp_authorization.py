"""Pruebas de vinculación MCP aisladas de usuarios reales."""

import pytest
from tinydb import TinyDB

from mcp_identity import MCPIdentity
from mcp_authorization import (
    MCPAuthorizationError,
    authorize_mcp_identity,
)


@pytest.fixture
def context(tmp_path):
    db = TinyDB(tmp_path / "mcp-authz.json")
    users = db.table("users")
    bindings = db.table("mcp_bindings")

    user_id = users.insert({
        "email": "demo@example.test",
        "role": "user",
        "is_active": True,
    })

    identity = MCPIdentity(
        subject="keycloak-sub-123",
        scopes=frozenset({
            "incidents:read",
            "incidents:write",
        }),
    )

    def authorize(scope="incidents:read", issuer="https://kc.test"):
        return authorize_mcp_identity(
            identity,
            issuer=issuer,
            required_scope=scope,
            bindings_table=bindings,
            users_table=users,
        )

    yield users, bindings, user_id, authorize
    db.close()


def link(bindings, user_id, scopes=None):
    bindings.insert({
        "issuer": "https://kc.test",
        "subject": "keycloak-sub-123",
        "user_id": user_id,
        "granted_scopes": (
            ["incidents:read"] if scopes is None else scopes
        ),
    })


def test_unlinked_identity_rejected(context):
    _, _, _, authorize = context
    with pytest.raises(MCPAuthorizationError):
        authorize()


def test_valid_explicit_link(context):
    _, bindings, user_id, authorize = context
    link(bindings, user_id)
    result = authorize()
    assert result.user_id == user_id
    assert result.role == "user"


def test_grant_missing_rejected(context):
    _, bindings, user_id, authorize = context
    link(bindings, user_id)
    with pytest.raises(MCPAuthorizationError):
        authorize("incidents:write")


def test_wrong_issuer_rejected(context):
    _, bindings, user_id, authorize = context
    link(bindings, user_id)
    with pytest.raises(MCPAuthorizationError):
        authorize(issuer="https://wrong.test")


def test_inactive_user_rejected(context):
    users, bindings, user_id, authorize = context
    link(bindings, user_id)
    users.update({"is_active": False}, doc_ids=[user_id])
    with pytest.raises(MCPAuthorizationError):
        authorize()


def test_duplicate_binding_rejected(context):
    _, bindings, user_id, authorize = context
    link(bindings, user_id)
    link(bindings, user_id)
    with pytest.raises(MCPAuthorizationError):
        authorize()


def test_unknown_user_rejected(context):
    _, bindings, _, authorize = context
    link(bindings, 99999)
    with pytest.raises(MCPAuthorizationError):
        authorize()
