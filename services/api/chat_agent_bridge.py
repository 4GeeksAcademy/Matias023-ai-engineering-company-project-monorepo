"""Puente entre sesiones WebSocket y el agente LangGraph existente."""

from agent_persistence import async_persistent_agent


async def run_chat_agent(
    *,
    question: str,
    session_id: str,
    token: str,
    approved_memories=None,
    service=None,
    database=None,
):
    """Ejecutar el grafo usando session_id como thread_id.

    Devuelve la salida del grafo con sus validaciones habituales.
    El transporte incremental se integrará después.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Pregunta obligatoria")

    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Sesión obligatoria")

    if not isinstance(token, str) or not token.strip():
        raise ValueError("Autenticación obligatoria")

    config = {
        "configurable": {
            "thread_id": session_id,
        }
    }

    context = {
        "token": token,
        "approved_memories": approved_memories or [],
    }

    kwargs = {}

    if service is not None:
        kwargs["service"] = service

    if database is not None:
        kwargs["database"] = database

    async with async_persistent_agent(**kwargs) as graph:
        result = await graph.ainvoke(
            {"question": question},
            config=config,
            context=context,
        )

    if not isinstance(result, dict):
        raise RuntimeError("Resultado del agente inválido")

    return result



async def stream_chat_agent(
    *,
    question: str,
    session_id: str,
    token: str,
    approved_memories=None,
    service=None,
    database=None,
):
    """Emitir fragmentos provisionales y resultado validado."""

    if not isinstance(question, str) or not question.strip():
        raise ValueError("Pregunta obligatoria")

    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Sesión obligatoria")

    if not isinstance(token, str) or not token.strip():
        raise ValueError("Autenticación obligatoria")

    config = {
        "configurable": {
            "thread_id": session_id,
        }
    }

    context = {
        "token": token,
        "approved_memories": approved_memories or [],
    }

    kwargs = {"streaming": True}

    if service is not None:
        kwargs["service"] = service

    if database is not None:
        kwargs["database"] = database

    final_state = None

    async with async_persistent_agent(**kwargs) as graph:
        async for mode, data in graph.astream(
            {"question": question},
            config=config,
            context=context,
            stream_mode=["custom", "updates"],
        ):
            if mode == "custom":
                if (
                    isinstance(data, dict)
                    and data.get("type") == "provisional_token"
                    and isinstance(data.get("token"), str)
                    and data["token"]
                ):
                    yield {
                        "kind": "token",
                        "text": data["token"],
                        "provisional": True,
                    }

            elif mode == "updates" and isinstance(data, dict):
                for changes in data.values():
                    if (
                        isinstance(changes, dict)
                        and "answer" in changes
                        and "abstained" in changes
                    ):
                        final_state = changes

        if final_state is None:
            snapshot = await graph.aget_state(config)
            final_state = dict(snapshot.values)

    if not isinstance(final_state.get("answer"), str):
        raise RuntimeError(
            "El agente no devolvió respuesta final"
        )

    yield {
        "kind": "final",
        "result": final_state,
        "provisional": False,
    }
