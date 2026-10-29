"""Seguridad WebSocket con JWT locales realmente firmados."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from starlette.websockets import WebSocketDisconnect

import security
from main import app
from chat_realtime import ChatSessionStore
from routers import chat_websocket as module


TEST_SECRET = "trackflow-test-key-only-not-production-2026"


def issue_token(
    *,
    secret=TEST_SECRET,
    expires_minutes=10,
    subject="7",
):
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes
    )

    return jwt.encode(
        {
            "sub": subject,
            "exp": expires,
        },
        secret,
        algorithm="HS256",
    )


@pytest.fixture
def environment(tmp_path, monkeypatch):
    store = ChatSessionStore(tmp_path / "signed_jwt.sqlite3")

    class Users:
        active = True

        def get(self, *, doc_id):
            if doc_id != 7:
                return None
            return {
                "is_active": self.active,
                "uuid": "test-user-uuid",
            }

    users = Users()

    monkeypatch.setattr(
        security,
        "_get_secret_key",
        lambda: TEST_SECRET,
    )

    monkeypatch.setattr(module, "users_table", users)

    monkeypatch.setattr(
        module,
        "document_to_dict",
        lambda document: document,
    )

    monkeypatch.setattr(
        module,
        "get_chat_store",
        lambda: store,
    )

    module._MANAGERS.clear()

    yield users

    module._MANAGERS.clear()


def connect_url(token):
    return (
        "/agent/chat/ws"
        f"?token={token}&client_id=signed_test_client"
    )


def test_valid_signed_jwt_opens_websocket(environment):
    token = issue_token()

    with TestClient(app) as client:
        with client.websocket_connect(connect_url(token)) as ws:
            snapshot = ws.receive_json()

    assert snapshot["event"] == "session_snapshot"
    assert snapshot["data"]["session_id"].startswith("chat_")


@pytest.mark.parametrize(
    "token",
    [
        issue_token(secret="wrong-signing-key"),
        issue_token(expires_minutes=-10),
        issue_token(subject="not-an-integer"),
    ],
)
def test_invalid_signed_jwt_is_rejected(environment, token):
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(connect_url(token)):
                pass

    assert error.value.code == 1008


def test_inactive_user_is_rejected(environment):
    environment.active = False

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(
                connect_url(issue_token())
            ):
                pass

    assert error.value.code == 1008


def test_valid_jwt_cannot_reuse_other_users_session(
    environment,
    monkeypatch,
):
    token = issue_token()

    with TestClient(app) as client:
        with client.websocket_connect(connect_url(token)) as ws:
            session_id = ws.receive_json()["data"]["session_id"]

    # El usuario con identidad 8 no es propietario de la sesión.
    other_user_token = issue_token(subject="8")

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(
                connect_url(other_user_token)
                + f"&session_id={session_id}"
            ):
                pass

    assert error.value.code == 1008
