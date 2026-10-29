
"""Pruebas del puente de streaming LangGraph."""

import asyncio
from contextlib import asynccontextmanager

import chat_agent_bridge


def test_streaming_and_final_result(monkeypatch):
    async def scenario():
        recorded = {}

        class FakeGraph:
            async def astream(
                self, payload, *, config, context, stream_mode
            ):
                recorded["thread_id"] = (
                    config["configurable"]["thread_id"]
                )
                recorded["modes"] = stream_mode

                yield (
                    "custom",
                    {
                        "type": "provisional_token",
                        "token": "Hola",
                    },
                )

                yield (
                    "custom",
                    {
                        "type": "provisional_token",
                        "token": " [1]",
                    },
                )

                yield (
                    "updates",
                    {
                        "generate": {
                            "answer": "Hola [1]",
                            "abstained": False,
                            "sources": [],
                        }
                    },
                )

        @asynccontextmanager
        async def fake_agent(**kwargs):
            recorded["streaming"] = kwargs["streaming"]
            yield FakeGraph()

        monkeypatch.setattr(
            chat_agent_bridge,
            "async_persistent_agent",
            fake_agent,
        )

        events = [
            event
            async for event in chat_agent_bridge.stream_chat_agent(
                question="Consulta",
                session_id="chat_123",
                token="token-prueba",
            )
        ]

        assert [e["kind"] for e in events] == [
            "token",
            "token",
            "final",
        ]

        assert events[-1]["result"]["answer"] == "Hola [1]"
        assert recorded["thread_id"] == "chat_123"
        assert recorded["streaming"] is True
        assert recorded["modes"] == ["custom", "updates"]

    asyncio.run(scenario())


def test_rejected_answer_remains_distinct(monkeypatch):
    async def scenario():
        class FakeGraph:
            async def astream(self, *args, **kwargs):
                yield (
                    "custom",
                    {
                        "type": "provisional_token",
                        "token": "Incorrecto",
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
        async def fake_agent(**kwargs):
            yield FakeGraph()

        monkeypatch.setattr(
            chat_agent_bridge,
            "async_persistent_agent",
            fake_agent,
        )

        events = [
            event
            async for event in chat_agent_bridge.stream_chat_agent(
                question="Consulta",
                session_id="chat_456",
                token="token-prueba",
            )
        ]

        assert events[0]["provisional"] is True
        assert events[-1]["kind"] == "final"
        assert events[-1]["result"]["abstained"] is True

    asyncio.run(scenario())
