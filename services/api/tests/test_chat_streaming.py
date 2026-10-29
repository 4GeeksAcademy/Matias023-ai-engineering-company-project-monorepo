"""Pruebas aisladas del streaming Gemini."""

import asyncio
from types import SimpleNamespace

import pytest

from chat_streaming import stream_gemini


class FakeModels:
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False
        self.calls = []

    async def generate_content_stream(self, *, model, contents):
        self.calls.append((model, contents))

        async def generator():
            try:
                for text in self.chunks:
                    yield SimpleNamespace(text=text)
            finally:
                self.closed = True

        return generator()


class FakeClient:
    def __init__(self, chunks):
        self.models = FakeModels(chunks)
        self.aio = SimpleNamespace(models=self.models)


def test_streaming_yields_real_chunks():
    async def scenario():
        client = FakeClient(["Hola", " ", "TrackFlow"])

        chunks = [
            text
            async for text in stream_gemini(
                client,
                "test-model",
                "Pregunta",
            )
        ]

        assert chunks == ["Hola", " ", "TrackFlow"]
        assert client.models.calls == [
            ("test-model", "Pregunta")
        ]
        assert client.models.closed

    asyncio.run(scenario())


def test_streaming_skips_empty_chunks():
    async def scenario():
        client = FakeClient(["Hola", None, "", " mundo"])

        chunks = [
            text
            async for text in stream_gemini(
                client,
                "test-model",
                "Pregunta",
            )
        ]

        assert chunks == ["Hola", " mundo"]
        assert client.models.closed

    asyncio.run(scenario())


def test_streaming_rejects_invalid_input():
    async def scenario():
        client = FakeClient(["Hola"])

        with pytest.raises(ValueError):
            async for _ in stream_gemini(
                client,
                "",
                "Pregunta",
            ):
                pass

    asyncio.run(scenario())


def test_streaming_cancellation_closes_iterator():
    async def scenario():
        started = asyncio.Event()
        closed = asyncio.Event()

        class BlockingModels:
            async def generate_content_stream(
                self, *, model, contents
            ):
                async def generator():
                    try:
                        yield SimpleNamespace(text="Primero")
                        started.set()
                        await asyncio.Event().wait()
                        yield SimpleNamespace(text="Segundo")
                    finally:
                        closed.set()

                return generator()

        client = SimpleNamespace(
            aio=SimpleNamespace(models=BlockingModels())
        )

        received = []

        async def consume():
            async for text in stream_gemini(
                client,
                "test-model",
                "Pregunta",
            ):
                received.append(text)

        task = asyncio.create_task(consume())

        await asyncio.wait_for(started.wait(), timeout=2)

        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)

        assert received == ["Primero"]
        assert closed.is_set()

    asyncio.run(scenario())
