"""Integración de eventos WebSocket y controlador."""

import asyncio

from fastapi.testclient import TestClient

from main import app
from chat_realtime import ChatSessionStore
from routers import chat_websocket as module


def test_websocket_dispatch_stream_and_interrupt(
    tmp_path, monkeypatch
):
    store = ChatSessionStore(tmp_path / "dispatch.sqlite3")
    monkeypatch.setattr(module, "get_chat_store", lambda: store)
    monkeypatch.setattr(module, "authenticate", lambda token: 7)

    started = asyncio.Event()

    async def producer():
        yield "Hola"
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(
        module,
        "get_chat_producer",
        lambda text, session_id, token: producer(),
    )

    module._MANAGERS.clear()

    with TestClient(app) as client:
        with client.websocket_connect(
            "/agent/chat/ws?client_id=cliente_a"
        ) as ws:
            ws.send_json({
                "event": "authenticate",
                "data": {"token": "test"},
            })
            snapshot = ws.receive_json()
            sid = snapshot["data"]["session_id"]

            ws.send_json({
                "event": "user_message",
                "data": {
                    "session_id": sid,
                    "text": "Pregunta",
                },
            })

            first = ws.receive_json()
            assert first["event"] == "token_chunk"
            assert first["data"]["token"] == "Hola"

            ws.send_json({
                "event": "interrupt_requested",
                "data": {
                    "session_id": sid,
                    "new_input": "",
                },
            })

            interrupted = ws.receive_json()
            assert interrupted["event"] == "generation_interrupted"
            assert interrupted["data"]["status"] == "interrupted"

    module._MANAGERS.clear()
