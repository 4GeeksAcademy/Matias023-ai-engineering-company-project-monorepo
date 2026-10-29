
"""Resultados provisionales y definitivos del chat."""

import asyncio

import pytest

from chat_generation import ChatGenerationManager
from chat_realtime import ChatPubSub, ChatSessionStore


def test_rejected_answer_replaces_provisional(tmp_path):
    async def scenario():
        store = ChatSessionStore(tmp_path / "final.sqlite3")
        bus = ChatPubSub()
        manager = ChatGenerationManager(store, bus)

        session = store.create(
            user_id=7,
            client_id="cliente_a",
        )

        sid = session.session_id
        queue = await bus.subscribe(sid)

        async def producer():
            yield {
                "kind": "token",
                "text": "Respuesta incorrecta",
                "provisional": True,
            }

            yield {
                "kind": "final",
                "result": {
                    "answer": "Información insuficiente",
                    "abstained": True,
                },
                "provisional": False,
            }

        await manager.start(
            session_id=sid,
            user_id=7,
            client_id="cliente_a",
            text="Consulta",
            producer=producer(),
        )

        await manager._tasks[sid]

        events = [
            await asyncio.wait_for(queue.get(), 1)
            for _ in range(3)
        ]

        assert [event["event"] for event in events] == [
            "token_chunk",
            "session_snapshot",
            "generation_completed",
        ]

        snapshot = events[1]
        assistant = snapshot["data"]["messages"][-1]

        assert assistant["content"] == (
            "Información insuficiente"
        )
        assert assistant["status"] == "completed"

        assert "Respuesta incorrecta" not in assistant["content"]

        await bus.unsubscribe(sid, queue)

    asyncio.run(scenario())


def test_missing_final_does_not_complete(tmp_path):
    async def scenario():
        store = ChatSessionStore(tmp_path / "missing.sqlite3")
        bus = ChatPubSub()
        manager = ChatGenerationManager(store, bus)

        session = store.create(
            user_id=7,
            client_id="cliente_a",
        )

        sid = session.session_id
        queue = await bus.subscribe(sid)

        async def producer():
            yield {
                "kind": "token",
                "text": "Provisional",
                "provisional": True,
            }

        await manager.start(
            session_id=sid,
            user_id=7,
            client_id="cliente_a",
            text="Consulta",
            producer=producer(),
        )

        with pytest.raises(RuntimeError):
            await manager._tasks[sid]

        events = []

        while not queue.empty():
            events.append(queue.get_nowait())

        assert not any(
            event["event"] == "generation_completed"
            for event in events
        )

        snapshot = store.snapshot(
            sid,
            user_id=7,
            client_id="cliente_a",
        )

        assert (
            snapshot["data"]["messages"][-1]["status"]
            == "interrupted"
        )

        await bus.unsubscribe(sid, queue)

    asyncio.run(scenario())
