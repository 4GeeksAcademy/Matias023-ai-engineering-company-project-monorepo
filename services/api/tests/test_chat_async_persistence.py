
"""Integración real del grafo con AsyncSqliteSaver."""

import asyncio
from types import SimpleNamespace

from agent_persistence import async_persistent_agent


def test_async_graph_checkpoint_and_resume(tmp_path):
    async def scenario():
        db = tmp_path / "agent_async.sqlite3"

        service = SimpleNamespace(
            threshold=0.54,
        )

        config = {
            "configurable": {
                "thread_id": "chat_test_async",
            }
        }

        async with async_persistent_agent(
            service=service,
            database=db,
        ) as graph:
            updates = [
                update
                async for update in graph.astream(
                    {"question": ""},
                    config=config,
                    stream_mode="updates",
                )
            ]

            assert updates
            assert "invalid" in updates[-1]

            state = await graph.aget_state(config)

            assert state.values["reason"] == (
                "pregunta_invalida"
            )

        assert db.is_file()

        # Comprobar recuperación desde una nueva conexión.
        async with async_persistent_agent(
            service=service,
            database=db,
        ) as graph:
            restored = await graph.aget_state(config)

            assert restored.values["reason"] == (
                "pregunta_invalida"
            )

    asyncio.run(scenario())
