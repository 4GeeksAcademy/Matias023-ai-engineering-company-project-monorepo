
"""WebSocket de sesiones TrackFlow.

F2: autenticación, aislamiento y recuperación.
La ejecución del agente se integra en F3.
"""

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket
from jose import JWTError, jwt
from starlette.websockets import WebSocketDisconnect

from chat_realtime import ChatPubSub, ChatSessionStore
from chat_generation import ChatGenerationManager
from chat_agent_bridge import stream_chat_agent
from database import users_table, document_to_dict
from security import decode_access_token


router = APIRouter(tags=["Chat WebSocket"])

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATABASE = DATA_DIR / "chat_sessions.sqlite3"

BUS = ChatPubSub()
_MANAGERS = {}


def get_generation_manager(store):
    """Compartir tareas por base de sesiones dentro del proceso."""
    key = str(store.path.resolve())
    manager = _MANAGERS.get(key)

    if manager is None:
        manager = ChatGenerationManager(store, BUS)
        _MANAGERS[key] = manager

    return manager


def get_chat_producer(text, session_id, token):
    """Ejecutar el agente existente con la sesión del WebSocket."""
    return stream_chat_agent(
        question=text,
        session_id=session_id,
        token=token,
    )



def get_chat_store():
    """Crear almacenamiento local privado."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    previous = os.umask(0o077)
    try:
        store = ChatSessionStore(DATABASE)
    finally:
        os.umask(previous)

    if DATABASE.exists():
        DATABASE.chmod(0o600)

    return store


def authenticate(token):
    """Validar JWT mediante las reglas locales o federadas existentes."""
    if not token:
        raise PermissionError("Autenticación requerida")

    try:
        header = jwt.get_unverified_header(token)
    except (JWTError, ValueError, TypeError):
        header = {}

    try:
        if header.get("alg") == "RS256":
            from mcp_federated_auth import resolve_federated_user_id

            # No omitir autorización por método o ruta.
            user_id = resolve_federated_user_id(
                token,
                method="GET",
                path="/agent/chat/ws",
            )
        else:
            user_id = decode_access_token(token)

    except (HTTPException, JWTError, ValueError, TypeError):
        raise PermissionError("Credenciales inválidas") from None

    user_doc = users_table.get(doc_id=user_id)

    if user_doc is None:
        raise PermissionError("Usuario no encontrado")

    user = document_to_dict(user_doc)

    if not user.get("is_active", False):
        raise PermissionError("Usuario inactivo")

    return user_id


@router.websocket("/agent/chat/ws")
async def chat_websocket(websocket: WebSocket):
    token = websocket.query_params.get("token")
    session_id = websocket.query_params.get("session_id")
    client_id = websocket.query_params.get("client_id")

    if not client_id or not client_id.strip():
        await websocket.close(code=1008)
        return

    try:
        user_id = authenticate(token)
        store = get_chat_store()

        if session_id:
            session = store.get(
                session_id,
                user_id=user_id,
                client_id=client_id,
            )
        else:
            session = store.create(
                user_id=user_id,
                client_id=client_id,
            )

        if session.status == "closed":
            await websocket.close(code=1008)
            return

    except (PermissionError, ValueError, OSError):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    manager = get_generation_manager(store)
    queue = await BUS.subscribe(session.session_id)

    async def publish_events():
        while True:
            event = await queue.get()
            await websocket.send_json(event)

    sender = asyncio.create_task(publish_events())

    try:
        await websocket.send_json(
            store.snapshot(
                session.session_id,
                user_id=user_id,
                client_id=client_id,
            )
        )

        while True:
            payload = await websocket.receive_json()

            if not isinstance(payload, dict):
                await websocket.close(code=1008)
                break

            event = payload.get("event")
            data = payload.get("data")

            if not isinstance(data, dict):
                await websocket.close(code=1008)
                break

            if data.get("session_id") != session.session_id:
                await websocket.close(code=1008)
                break

            if event == "user_message":
                text = data.get("text")

                if (
                    not isinstance(text, str)
                    or not text.strip()
                    or len(text) > 1000
                ):
                    await websocket.close(code=1008)
                    break

                try:
                    producer = get_chat_producer(
                        text,
                        session.session_id,
                        token,
                    )
                except RuntimeError:
                    await websocket.close(code=1013)
                    break

                try:
                    await manager.start(
                        session_id=session.session_id,
                        user_id=user_id,
                        client_id=client_id,
                        text=text,
                        producer=producer,
                    )
                except ValueError:
                    await websocket.close(code=1008)
                    break

                continue

            if event == "interrupt_requested":
                new_input = data.get("new_input")

                if not isinstance(new_input, str):
                    await websocket.close(code=1008)
                    break

                await manager.interrupt(
                    session_id=session.session_id,
                    user_id=user_id,
                    client_id=client_id,
                )
                continue

            await websocket.close(code=1008)
            break

    except WebSocketDisconnect:
        pass

    finally:
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)
        await BUS.unsubscribe(session.session_id, queue)
