"""Evidencia OWASP: autenticacion negativa y Origin WebSocket."""

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from chat_realtime import ChatSessionStore
from main import app
from routers import chat_websocket as module


@pytest.fixture
def environment(tmp_path, monkeypatch):
    store = ChatSessionStore(
        tmp_path / "owasp_negative_ws.sqlite3"
    )

    def strict_authenticate(token):
        if token != "test-jwt":
            raise PermissionError("Token invalido")
        return 7

    monkeypatch.setattr(
        module, "get_chat_store", lambda: store
    )
    monkeypatch.setattr(
        module, "authenticate", strict_authenticate
    )

    return TestClient(app)


@pytest.mark.parametrize(
    "message",
    [
        "{invalid-json",
        json.dumps({"event": "user_message", "data": {}}),
        json.dumps({"event": "authenticate", "data": {}}),
        json.dumps({
            "event": "authenticate",
            "data": {"token": "invalid-jwt"},
        }),
        json.dumps({
            "event": "authenticate",
            "data": {"token": 123},
        }),
        json.dumps({
            "event": "authenticate",
            "data": {"token": "test-jwt"},
        }) + (" " * 4097),
    ],
    ids=[
        "json-malformado",
        "evento-inicial-incorrecto",
        "token-ausente",
        "token-invalido",
        "token-no-string",
        "mensaje-demasiado-largo",
    ],
)
def test_rechaza_autenticacion_inicial_invalida(
    environment, message
):
    with environment.websocket_connect(
        "/agent/chat/ws?client_id=owasp_negative"
    ) as ws:
        ws.send_text(message)

        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()

        assert error.value.code == 1008


def test_rechaza_jwt_en_url(environment):
    with pytest.raises(WebSocketDisconnect) as error:
        with environment.websocket_connect(
            "/agent/chat/ws"
            "?client_id=owasp_negative&token=test-jwt"
        ):
            pass

    assert error.value.code == 1008


def test_rechaza_origin_externo_aun_con_jwt_valido(
    environment, monkeypatch
):
    monkeypatch.setenv(
        "WS_ALLOWED_ORIGINS", "http://localhost:3001"
    )

    with pytest.raises(WebSocketDisconnect) as error:
        with environment.websocket_connect(
            "/agent/chat/ws?client_id=owasp_origin",
            headers={"origin": "https://evil.example"},
        ):
            pass

    assert error.value.code == 1008


def test_permite_origin_autorizado_con_jwt_valido(
    environment, monkeypatch
):
    monkeypatch.setenv(
        "WS_ALLOWED_ORIGINS", "http://localhost:3001"
    )

    with environment.websocket_connect(
        "/agent/chat/ws?client_id=owasp_origin_allowed",
        headers={"origin": "http://localhost:3001"},
    ) as ws:
        ws.send_json({
            "event": "authenticate",
            "data": {"token": "test-jwt"},
        })

        response = ws.receive_json()
        assert response["event"] == "session_snapshot"
