
"""Recuperación del chat cuando falla Gemini/LangGraph."""

import asyncio

from chat_generation import ChatGenerationManager
from chat_realtime import ChatPubSub, ChatSessionStore


def test_producer_failure_notifies_and_cleans_content(tmp_path):
    async def scenario():
        store = ChatSessionStore(tmp_path / "failure.sqlite3")
        bus = ChatPubSub()
        manager = ChatGenerationManager(store, bus)

        session = store.create(
            user_id=7,
            client_id="cliente_test",
        )

        sid = session.session_id
        queue = await bus.subscribe(sid)

        async def producer():
            yield {
                "kind": "token",
                "text": "Texto incorrecto sin verificar",
                "provisional": True,
            }
            raise RuntimeError("Fallo simulado de Gemini")

        await manager.start(
            session_id=sid,
            user_id=7,
            client_id="cliente_test",
            text="Consulta",
            producer=producer(),
        )

        try:
            await manager._tasks[sid]
        except RuntimeError:
            pass
        else:
            raise AssertionError("No se propagó el error")

        events = []

        while not queue.empty():
            events.append(queue.get_nowait())

        assert [event["event"] for event in events] == [
            "token_chunk",
            "session_snapshot",
            "generation_interrupted",
        ]

        snapshot = events[1]
        assistant = snapshot["data"]["messages"][-1]

        assert assistant["status"] == "interrupted"
        assert "Texto incorrecto" not in assistant["content"]
        assert "No fue posible" in assistant["content"]

        assert events[2]["data"]["status"] == "interrupted"

        restored = store.snapshot(
            sid,
            user_id=7,
            client_id="cliente_test",
        )

        assert (
            restored["data"]["messages"][-1]["content"]
            == assistant["content"]
        )

        await bus.unsubscribe(sid, queue)

    asyncio.run(scenario())


def test_user_cancellation_preserves_existing_protocol(tmp_path):
    async def scenario():
        store = ChatSessionStore(tmp_path / "cancel.sqlite3")
        bus = ChatPubSub()
        manager = ChatGenerationManager(store, bus)

        session = store.create(
            user_id=7,
            client_id="cliente_test",
        )
        sid = session.session_id
        queue = await bus.subscribe(sid)

        started = asyncio.Event()

        async def producer():
            yield "Fragmento"
            started.set()
            await asyncio.Event().wait()

        await manager.start(
            session_id=sid,
            user_id=7,
            client_id="cliente_test",
            text="Consulta",
            producer=producer(),
        )

        await asyncio.wait_for(started.wait(), timeout=2)

        interrupted = await manager.interrupt(
            session_id=sid,
            user_id=7,
            client_id="cliente_test",
        )

        assert interrupted is True

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        assert [event["event"] for event in events] == [
            "token_chunk",
            "generation_interrupted",
        ]

        await bus.unsubscribe(sid, queue)

    asyncio.run(scenario())
