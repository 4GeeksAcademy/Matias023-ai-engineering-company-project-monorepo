"""Productor asíncrono de fragmentos Gemini para TrackFlow."""

import asyncio
from collections.abc import AsyncIterator


async def stream_gemini(
    client,
    model: str,
    prompt: str,
    *,
    config=None,
) -> AsyncIterator[str]:
    """Consumir fragmentos reales del SDK google-genai.

    El cliente y modelo se inyectan desde el agente existente.
    No crea otro agente ni modifica sus herramientas.
    """
    if not model or not prompt:
        raise ValueError("Modelo y prompt obligatorios")

    kwargs = {
        "model": model,
        "contents": prompt,
    }

    if config is not None:
        kwargs["config"] = config

    stream = await client.aio.models.generate_content_stream(
        **kwargs
    )

    try:
        async for chunk in stream:
            text = getattr(chunk, "text", None)

            if isinstance(text, str) and text:
                yield text
    except asyncio.CancelledError:
        raise
    finally:
        close = getattr(stream, "aclose", None)
        if callable(close):
            await close()


async def stream_trackflow_gemini(
    generator,
    prompt: str,
) -> AsyncIterator[str]:
    """Streaming con la configuración original de TrackFlow.

    Reutiliza la instancia GeminiGenerator existente.
    No altera el método síncrono __call__.
    """
    import os

    from dotenv import load_dotenv
    from google import genai
    from google.genai import types

    from generate import (
        ENV_FILE,
        SYSTEM_PROMPT,
    )

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Prompt inválido")

    if generator.client is None:
        load_dotenv(ENV_FILE)

        key = os.getenv("GEMINI_API_KEY")

        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY no configurada"
            )

        generator.client = genai.Client(api_key=key)

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0,
        max_output_tokens=1024,
    )

    async for chunk in stream_gemini(
        generator.client,
        generator.model,
        prompt,
        config=config,
    ):
        yield chunk
