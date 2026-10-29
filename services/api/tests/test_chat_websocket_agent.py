"""WebSocket conectado al streaming del agente TrackFlow."""

import asyncio

from fastapi.testclient import TestClient

from main import app
from chat_realtime import ChatSessionStore
from routers import chat_websocket as module


def test_chat_agent_verified_answer_and_reconnection(
    tmp_path, monkeypatch
):
    store = ChatSessionStore(tmp_path / "agent_ws.sqlite3")

    monkeypatch.setattr(
        module, "get_chat_store", lambda: store
    )
    monkeypatch.setattr(
        module, "authenticate", lambda token: 7
    )

    async def fake_agent(
        *, question, session_id, token, **kwargs
    ):
        assert question == "Consulta documental"
        assert token == "token-prueba"

        yield {
            "kind": "token",
            "text": "Provisional",
            "provisional": True,
        }

        yield {
            "kind": "final",
            "result": {
                "answer": "Respuesta validada [1]",
                "abstained": False,
                "sources": [],
            },
            "provisional": False,
        }

    monkeypatch.setattr(
        module, "stream_chat_agent", fake_agent
    )

    module._MANAGERS.clear()

    with TestClient(app) as client:
        url = (
            "/agent/chat/ws"
            "?client_id=cliente_a"
        )

        with client.websocket_connect(url) as ws:
            ws.send_json({
                "event": "authenticate",
                "data": {"token": "token-prueba"},
            })
            initial = ws.receive_json()
            assert initial["event"] == "session_snapshot"
            sid = initial["data"]["session_id"]

            ws.send_json({
                "event": "user_message",
                "data": {
                    "session_id": sid,
                    "text": "Consulta documental",
                },
            })

            events = [
                ws.receive_json()
                for _ in range(3)
            ]

            assert [event["event"] for event in events] == [
                "token_chunk",
                "session_snapshot",
                "generation_completed",
            ]

            assert events[0]["data"]["token"] == (
                "Provisional"
            )

            final_messages = events[1]["data"]["messages"]

            assert final_messages[-1]["content"] == (
                "Respuesta validada [1]"
            )

            assert final_messages[-1]["status"] == (
                "completed"
            )

        # La misma sesión debe recuperar su historial.
        with client.websocket_connect(
            url + f"&session_id={sid}"
        ) as ws:
            ws.send_json({
                "event": "authenticate",
                "data": {"token": "token-prueba"},
            })
            restored = ws.receive_json()

            assert restored["event"] == (
                "session_snapshot"
            )

            assert restored["data"]["session_id"] == sid

            assert restored["data"]["messages"][-1][
                "content"
            ] == "Respuesta validada [1]"

    module._MANAGERS.clear()


def test_chat_agent_rejected_answer_is_reconciled(
    tmp_path, monkeypatch
):
    store = ChatSessionStore(
        tmp_path / "agent_rejected.sqlite3"
    )

    monkeypatch.setattr(
        module, "get_chat_store", lambda: store
    )
    monkeypatch.setattr(
        module, "authenticate", lambda token: 7
    )

    async def rejected_agent(**kwargs):
        yield {
            "kind": "token",
            "text": "Respuesta no verificada",
            "provisional": True,
        }

        yield {
            "kind": "final",
            "result": {
                "answer": "Información insuficiente",
                "abstained": True,
                "reason": "sin_respaldo",
            },
            "provisional": False,
        }

    monkeypatch.setattr(
        module, "stream_chat_agent", rejected_agent
    )

    module._MANAGERS.clear()

    with TestClient(app) as client:
        with client.websocket_connect(
            "/agent/chat/ws"
            "?client_id=cliente_a"
        ) as ws:
            ws.send_json({
                "event": "authenticate",
                "data": {"token": "token-prueba"},
            })
            initial = ws.receive_json()
            sid = initial["data"]["session_id"]

            ws.send_json({
                "event": "user_message",
                "data": {
                    "session_id": sid,
                    "text": "Consulta",
                },
            })

            events = [
                ws.receive_json()
                for _ in range(3)
            ]

            assert events[0]["event"] == "token_chunk"
            assert events[1]["event"] == (
                "session_snapshot"
            )
            assert events[2]["event"] == (
                "generation_completed"
            )

            final_message = events[1]["data"]["messages"][-1]

            assert final_message["content"] == (
                "Información insuficiente"
            )

            assert "Respuesta no verificada" not in (
                final_message["content"]
            )

    module._MANAGERS.clear()



def test_owasp_websocket_no_expone_respuesta_rechazada(
    tmp_path, monkeypatch
):
    """Prueba integrada: WebSocket y puente real ante rechazo."""
    from contextlib import asynccontextmanager
    import chat_agent_bridge

    marker = "CONTENIDO_RECHAZADO_OWASP"
    store = ChatSessionStore(tmp_path / "owasp_streaming.sqlite3")

    monkeypatch.setattr(
        module, "get_chat_store", lambda: store
    )
    monkeypatch.setattr(
        module, "authenticate", lambda token: 7
    )

    class FakeGraph:
        async def astream(self, *args, **kwargs):
            yield (
                "custom",
                {
                    "type": "provisional_token",
                    "token": marker,
                },
            )
            yield (
                "updates",
                {
                    "generate": {
                        "answer": "Información insuficiente",
                        "abstained": True,
                        "reason": "sin_respaldo",
                    }
                },
            )

    @asynccontextmanager
    async def fake_persistent_agent(**kwargs):
        yield FakeGraph()

    monkeypatch.setattr(
        chat_agent_bridge,
        "async_persistent_agent",
        fake_persistent_agent,
    )

    # IMPORTANTE: no reemplazar stream_chat_agent.
    # La ruta WebSocket debe utilizar el puente real.
    module._MANAGERS.clear()

    try:
        with TestClient(app) as client:
            with client.websocket_connect(
                "/agent/chat/ws"
                "?client_id=cliente_owasp"
            ) as ws:
                ws.send_json({
                    "event": "authenticate",
                    "data": {"token": "token-prueba"},
                })
                initial = ws.receive_json()
                assert initial["event"] == "session_snapshot"

                session_id = initial["data"]["session_id"]

                ws.send_json({
                    "event": "user_message",
                    "data": {
                        "session_id": session_id,
                        "text": "Consulta sintética de seguridad",
                    },
                })

                events = [
                    ws.receive_json()
                    for _ in range(2)
                ]

                assert [event["event"] for event in events] == [
                    "session_snapshot",
                    "generation_completed",
                ], (
                    "El WebSocket emitió eventos inesperados "
                    "durante una generación rechazada"
                )

                assert not any(
                    event["event"] == "token_chunk"
                    for event in events
                )

                assert marker not in str(events), (
                    "El cliente recibió contenido rechazado"
                )

                final_message = (
                    events[0]["data"]["messages"][-1]
                )

                assert final_message["content"] == (
                    "Información insuficiente"
                )
    finally:
        module._MANAGERS.clear()
