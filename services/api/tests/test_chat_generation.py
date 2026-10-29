"""Pruebas del controlador de generaciones del chat."""

import asyncio

from chat_generation import ChatGenerationManager
from chat_realtime import ChatPubSub, ChatSessionStore


def setup(tmp_path):
    store = ChatSessionStore(tmp_path / "generation.sqlite3")
    bus = ChatPubSub()
    manager = ChatGenerationManager(store, bus)

    session = store.create(
        user_id=7,
        client_id="cliente_a",
    )

    return manager, store, bus, session.session_id


def test_generation_completed(tmp_path):
    async def scenario():
        manager, store, bus, session_id = setup(tmp_path)
        queue = await bus.subscribe(session_id)

        async def producer():
            yield "Hola"
            yield " TrackFlow"

        await manager.start(
            session_id=session_id,
            user_id=7,
            client_id="cliente_a",
            text="Hola",
            producer=producer(),
        )

        await manager._tasks[session_id]

        events = [
            await asyncio.wait_for(queue.get(), 1)
            for _ in range(3)
        ]

        assert [e["event"] for e in events] == [
            "token_chunk",
            "token_chunk",
            "generation_completed",
        ]

        assert [
            e["data"]["sequence"]
            for e in events[:2]
        ] == [1, 2]

        snapshot = store.snapshot(
            session_id,
            user_id=7,
            client_id="cliente_a",
        )

        assistant = snapshot["data"]["messages"][-1]

        assert assistant["content"] == "Hola TrackFlow"
        assert assistant["status"] == "completed"

        await bus.unsubscribe(session_id, queue)

    asyncio.run(scenario())


def test_interrupt_stops_producer(tmp_path):
    async def scenario():
        manager, store, bus, session_id = setup(tmp_path)
        queue = await bus.subscribe(session_id)

        started = asyncio.Event()
        closed = asyncio.Event()

        async def producer():
            try:
                yield "Primero"
                started.set()
                await asyncio.Event().wait()
                yield "Segundo"
            finally:
                closed.set()

        await manager.start(
            session_id=session_id,
            user_id=7,
            client_id="cliente_a",
            text="Pregunta",
            producer=producer(),
        )

        await asyncio.wait_for(started.wait(), 1)

        result = await manager.interrupt(
            session_id=session_id,
            user_id=7,
            client_id="cliente_a",
        )

        assert result is True
        assert closed.is_set()

        events = []

        while not queue.empty():
            events.append(queue.get_nowait())

        assert [e["event"] for e in events] == [
            "token_chunk",
            "generation_interrupted",
        ]

        snapshot = store.snapshot(
            session_id,
            user_id=7,
            client_id="cliente_a",
        )

        assistant = snapshot["data"]["messages"][-1]

        assert assistant["content"] == "Primero"
        assert assistant["status"] == "interrupted"

        await bus.unsubscribe(session_id, queue)

    asyncio.run(scenario())


def test_rejects_concurrent_generation(tmp_path):
    async def scenario():
        manager, _, _, session_id = setup(tmp_path)
        started = asyncio.Event()

        async def blocking():
            yield "Uno"
            started.set()
            await asyncio.Event().wait()

        await manager.start(
            session_id=session_id,
            user_id=7,
            client_id="cliente_a",
            text="Primera",
            producer=blocking(),
        )

        await asyncio.wait_for(started.wait(), 1)

        try:
            await manager.start(
                session_id=session_id,
                user_id=7,
                client_id="cliente_a",
                text="Segunda",
                producer=blocking(),
            )
        except ValueError as exc:
            assert str(exc) == "Generación activa"
        else:
            raise AssertionError(
                "Se permitió generación concurrente"
            )

        assert await manager.interrupt(
            session_id=session_id,
            user_id=7,
            client_id="cliente_a",
        )

    asyncio.run(scenario())
