"""Pruebas del transporte WebSocket TrackFlow."""

from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from chat_realtime import ChatSessionStore
from main import app
from routers import chat_websocket as module


@pytest.fixture
def environment(tmp_path, monkeypatch):
    store = ChatSessionStore(tmp_path / "sessions.sqlite3")

    monkeypatch.setattr(
        module,
        "get_chat_store",
        lambda: store,
    )

    def fake_authenticate(token):
        if token == "test-user-7":
            return 7
        if token == "test-user-8":
            return 8
        raise PermissionError("Token inválido")

    monkeypatch.setattr(
        module,
        "authenticate",
        fake_authenticate,
    )

    return TestClient(app), store


def url(token=None, session_id=None, client_id="cliente_a"):
    params = {"client_id": client_id}

    if session_id is not None:
        params["session_id"] = session_id

    return "/agent/chat/ws?" + urlencode(params)


def test_valid_connection_receives_snapshot(environment):
    client, _ = environment

    with client.websocket_connect(url("test-user-7")) as ws:
        ws.send_json({
            "event": "authenticate",
            "data": {"token": "test-user-7"},
        })
        event = ws.receive_json()

        assert event["event"] == "session_snapshot"
        assert event["data"]["messages"] == []
        assert event["data"]["session_id"].startswith("chat_")


def test_missing_token_rejected(environment):
    client, _ = environment

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(url()) as ws:
            ws.send_json({
                "event": "authenticate",
                "data": {},
            })
            ws.receive_json()

    assert error.value.code == 1008


def test_invalid_token_rejected(environment):
    client, _ = environment

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(url("invalid-token")) as ws:
            ws.send_json({
                "event": "authenticate",
                "data": {"token": "invalid-token"},
            })
            ws.receive_json()

    assert error.value.code == 1008


def test_reconnect_recovers_history(environment):
    client, store = environment

    with client.websocket_connect(url("test-user-7")) as ws:
        ws.send_json({
            "event": "authenticate",
            "data": {"token": "test-user-7"},
        })
        snapshot = ws.receive_json()
        session_id = snapshot["data"]["session_id"]

    store.add_message(
        session_id,
        user_id=7,
        client_id="cliente_a",
        role="user",
        content="Hola TrackFlow",
    )

    with client.websocket_connect(
        url("test-user-7", session_id)
    ) as ws:
        ws.send_json({
            "event": "authenticate",
            "data": {"token": "test-user-7"},
        })
        snapshot = ws.receive_json()

    assert snapshot["event"] == "session_snapshot"
    assert snapshot["data"]["session_id"] == session_id
    assert snapshot["data"]["messages"][0]["content"] == "Hola TrackFlow"


def test_other_user_cannot_access_session(environment):
    client, _ = environment

    with client.websocket_connect(url("test-user-7")) as ws:
        ws.send_json({
            "event": "authenticate",
            "data": {"token": "test-user-7"},
        })
        session_id = ws.receive_json()["data"]["session_id"]

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(
            url("test-user-8", session_id)
        ) as ws:
            ws.send_json({
                "event": "authenticate",
                "data": {"token": "test-user-8"},
            })
            ws.receive_json()

    assert error.value.code == 1008


def test_other_client_cannot_access_session(environment):
    client, _ = environment

    with client.websocket_connect(url("test-user-7")) as ws:
        ws.send_json({
            "event": "authenticate",
            "data": {"token": "test-user-7"},
        })
        session_id = ws.receive_json()["data"]["session_id"]

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(
            url("test-user-7", session_id, "cliente_b")
        ) as ws:
            ws.send_json({
                "event": "authenticate",
                "data": {"token": "test-user-7"},
            })
            ws.receive_json()

    assert error.value.code == 1008


def test_closed_session_rejected(environment):
    client, store = environment

    with client.websocket_connect(url("test-user-7")) as ws:
        ws.send_json({
            "event": "authenticate",
            "data": {"token": "test-user-7"},
        })
        session_id = ws.receive_json()["data"]["session_id"]

    store.set_status(
        session_id,
        user_id=7,
        client_id="cliente_a",
        status="closed",
    )

    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(
            url("test-user-7", session_id)
        ) as ws:
            ws.send_json({
                "event": "authenticate",
                "data": {"token": "test-user-7"},
            })
            ws.receive_json()

    assert error.value.code == 1008


def test_wrong_session_message_rejected(environment):
    client, _ = environment

    with client.websocket_connect(url("test-user-7")) as ws:
        ws.send_json({
            "event": "authenticate",
            "data": {"token": "test-user-7"},
        })
        ws.receive_json()

        ws.send_json({
            "event": "user_message",
            "data": {
                "session_id": "chat_otra",
                "text": "Hola",
            },
        })

        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()

        assert error.value.code == 1008
