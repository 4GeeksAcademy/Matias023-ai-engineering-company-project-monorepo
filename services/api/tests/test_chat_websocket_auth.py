"""Autenticación real del WebSocket, sin credenciales externas."""

import pytest

from routers import chat_websocket as module


def configure(monkeypatch, *, active=True):
    class FakeUsers:
        def get(self, *, doc_id):
            if doc_id != 7:
                return None
            return {"is_active": active}

    monkeypatch.setattr(module, "users_table", FakeUsers())
    monkeypatch.setattr(
        module,
        "document_to_dict",
        lambda item: item,
    )


def test_valid_local_token(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(
        module.jwt,
        "get_unverified_header",
        lambda token: {"alg": "HS256"},
    )
    monkeypatch.setattr(
        module,
        "decode_access_token",
        lambda token: 7,
    )

    assert module.authenticate("local-test") == 7


def test_valid_federated_token_uses_method_and_path(monkeypatch):
    configure(monkeypatch)

    import mcp_federated_auth

    calls = {}

    monkeypatch.setattr(
        module.jwt,
        "get_unverified_header",
        lambda token: {"alg": "RS256"},
    )

    def resolve(token, *, method, path):
        calls.update(
            token=token,
            method=method,
            path=path,
        )
        return 7

    monkeypatch.setattr(
        mcp_federated_auth,
        "resolve_federated_user_id",
        resolve,
    )

    assert module.authenticate("federated-test") == 7
    assert calls == {
        "token": "federated-test",
        "method": "GET",
        "path": "/agent/chat/ws",
    }


def test_invalid_federated_token_rejected(monkeypatch):
    configure(monkeypatch)

    import mcp_federated_auth
    from fastapi import HTTPException

    monkeypatch.setattr(
        module.jwt,
        "get_unverified_header",
        lambda token: {"alg": "RS256"},
    )

    def reject(*args, **kwargs):
        raise HTTPException(status_code=403)

    monkeypatch.setattr(
        mcp_federated_auth,
        "resolve_federated_user_id",
        reject,
    )

    with pytest.raises(PermissionError):
        module.authenticate("invalid-federated")


@pytest.mark.parametrize("algorithm", ["HS256", "RS256"])
def test_inactive_user_rejected(monkeypatch, algorithm):
    configure(monkeypatch, active=False)

    monkeypatch.setattr(
        module.jwt,
        "get_unverified_header",
        lambda token: {"alg": algorithm},
    )

    monkeypatch.setattr(
        module,
        "decode_access_token",
        lambda token: 7,
    )

    import mcp_federated_auth

    monkeypatch.setattr(
        mcp_federated_auth,
        "resolve_federated_user_id",
        lambda *args, **kwargs: 7,
    )

    with pytest.raises(PermissionError):
        module.authenticate("test-token")


def test_missing_token_rejected():
    with pytest.raises(PermissionError):
        module.authenticate(None)
