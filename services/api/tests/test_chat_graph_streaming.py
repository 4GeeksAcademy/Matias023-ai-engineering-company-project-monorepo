
"""Streaming real del nodo LangGraph, sin llamadas a Gemini."""

import asyncio
from types import SimpleNamespace

import agent_graph
import chat_streaming


def test_langgraph_streams_and_validates(monkeypatch):
    async def scenario():
        class Retriever:
            def retrieve(self, *args, **kwargs):
                return [{
                    "text": "Documento de prueba",
                    "source_document": "documento",
                    "source_file": "documento.md",
                    "section": "Prueba",
                    "chunk_index": 0,
                    "score": 0.99,
                }]

        service = SimpleNamespace(
            retriever=Retriever(),
            generator=object(),
            threshold=0.54,
        )

        async def fake_stream(generator, prompt):
            yield "Respuesta"
            yield " [1]"

        monkeypatch.setattr(
            chat_streaming,
            "stream_trackflow_gemini",
            fake_stream,
        )

        monkeypatch.setattr(
            agent_graph,
            "_unsupported_inbound_la",
            lambda *args: False,
        )

        monkeypatch.setattr(
            agent_graph,
            "verify_answer",
            lambda *args: (True, "ok", [1]),
        )

        graph = agent_graph.build_agent(
            service=service,
            streaming=True,
        )

        events = []

        async for event in graph.astream(
            {"question": "Consulta documental"},
            config={
                "configurable": {
                    "thread_id": "chat_graph_test",
                }
            },
            stream_mode=["custom", "updates"],
        ):
            events.append(event)

        tokens = [
            data["token"]
            for mode, data in events
            if mode == "custom"
            and data.get("type") == "provisional_token"
        ]

        assert tokens == ["Respuesta", " [1]"]

        updates = [
            data
            for mode, data in events
            if mode == "updates"
        ]

        generated = [
            item["generate"]
            for item in updates
            if "generate" in item
        ]

        assert generated
        assert generated[-1]["answer"] == "Respuesta [1]"
        assert generated[-1]["abstained"] is False

    asyncio.run(scenario())
