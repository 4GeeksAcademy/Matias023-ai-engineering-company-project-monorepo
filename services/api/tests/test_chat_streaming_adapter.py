
"""Contrato del adaptador Gemini TrackFlow."""

import asyncio
from types import SimpleNamespace

from chat_streaming import stream_trackflow_gemini


class FakeModels:
    def __init__(self):
        self.calls = []
        self.closed = False

    async def generate_content_stream(self, **kwargs):
        self.calls.append(kwargs)

        async def chunks():
            try:
                yield SimpleNamespace(text="Hola")
                yield SimpleNamespace(text=" TrackFlow")
            finally:
                self.closed = True

        return chunks()


class FakeClient:
    def __init__(self):
        self.models = FakeModels()
        self.aio = SimpleNamespace(models=self.models)


def test_preserves_trackflow_configuration():
    async def scenario():
        from generate import SYSTEM_PROMPT

        client = FakeClient()

        generator = SimpleNamespace(
            client=client,
            model="modelo-prueba",
        )

        output = [
            text
            async for text in stream_trackflow_gemini(
                generator,
                "Pregunta sobre devoluciones",
            )
        ]

        assert output == [
            "Hola",
            " TrackFlow",
        ]

        assert len(client.models.calls) == 1

        call = client.models.calls[0]

        assert call["model"] == "modelo-prueba"
        assert call["contents"] == (
            "Pregunta sobre devoluciones"
        )

        config = call["config"]

        assert config.system_instruction == SYSTEM_PROMPT
        assert config.temperature == 0
        assert config.max_output_tokens == 1024

        assert client.models.closed

    asyncio.run(scenario())


def test_rejects_empty_prompt():
    async def scenario():
        import pytest

        generator = SimpleNamespace(
            client=FakeClient(),
            model="modelo-prueba",
        )

        with pytest.raises(ValueError):
            async for _ in stream_trackflow_gemini(
                generator,
                "   ",
            ):
                pass

    asyncio.run(scenario())
