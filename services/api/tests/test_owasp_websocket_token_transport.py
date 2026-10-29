"""Pruebas OWASP: JWT fuera de la URL WebSocket."""

from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from chat_realtime import ChatSessionStore
from routers import chat_websocket as module


def test_websocket_autentica_por_primer_mensaje(
    tmp_path, monkeypatch
):
    """El handshake no debe requerir JWT en la URL."""

    store = ChatSessionStore(
        tmp_path / "owasp_auth_transport.sqlite3"
    )

    monkeypatch.setattr(
        module, "get_chat_store", lambda: store
    )
    def strict_authenticate(token):
        if token != "test-jwt":
            raise PermissionError("Token ausente o inválido")
        return 7

    monkeypatch.setattr(
        module, "authenticate", strict_authenticate
    )

    module._MANAGERS.clear()

    try:
        with TestClient(app) as client:
            with client.websocket_connect(
                "/agent/chat/ws?client_id=owasp_client"
            ) as ws:
                ws.send_json({
                    "event": "authenticate",
                    "data": {"token": "test-jwt"},
                })

                response = ws.receive_json()

                assert response["event"] == (
                    "session_snapshot"
                )
    finally:
        module._MANAGERS.clear()


def test_frontend_no_incluye_jwt_en_url_websocket():
    """La URL de conexión no debe transportar el JWT."""

    path = (
        Path(__file__).resolve().parents[3]
        / "uis/backoffice/src/pages/RagAssistantPage.tsx"
    )

    source = path.read_text(encoding="utf-8")

    assert "searchParams.set('token'," not in source
    assert 'searchParams.set("token",' not in source
