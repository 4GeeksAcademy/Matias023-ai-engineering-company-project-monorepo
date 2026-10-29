"""Pruebas del puente entre ChatSession y LangGraph."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import chat_agent_bridge
from chat_agent_bridge import run_chat_agent


def test_session_id_is_langgraph_thread_id(monkeypatch):
    async def scenario():
        calls = {}

        class FakeGraph:
            async def ainvoke(self, payload, *, config, context):
                calls["payload"] = payload
                calls["config"] = config
                calls["context"] = context

                return {
                    "answer": "Respuesta validada",
                    "abstained": False,
                    "sources": [],
                }

        @asynccontextmanager
        async def fake_persistent_agent(**kwargs):
            calls["kwargs"] = kwargs
            yield FakeGraph()

        monkeypatch.setattr(
            chat_agent_bridge,
            "async_persistent_agent",
            fake_persistent_agent,
        )

        result = await run_chat_agent(
            question="Consulta",
            session_id="chat_123",
            token="token-prueba",
        )

        assert calls["payload"] == {
            "question": "Consulta"
        }

        assert calls["config"]["configurable"]["thread_id"] == (
            "chat_123"
        )

        assert calls["context"]["token"] == "token-prueba"

        assert result["answer"] == "Respuesta validada"

    asyncio.run(scenario())


def test_real_graph_execution_without_llm(tmp_path):
    async def scenario():
        service = SimpleNamespace(
            threshold=0.54,
        )

        # Una pregunta excesivamente larga sigue la ruta
        # de validación del grafo, sin consultar Gemini.
        result = await run_chat_agent(
            question="x" * 1001,
            session_id="chat_test_bridge",
            token="token-simulado",
            service=service,
            database=tmp_path / "bridge.sqlite3",
        )

        assert result["reason"] == "pregunta_invalida"
        assert result["abstained"] is True

    asyncio.run(scenario())


def test_rejects_missing_session():
    async def scenario():
        with pytest.raises(ValueError):
            await run_chat_agent(
                question="Hola",
                session_id="",
                token="token",
            )

    asyncio.run(scenario())
