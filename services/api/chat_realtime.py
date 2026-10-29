"""Contrato y almacenamiento del chat WebSocket TrackFlow."""

import asyncio
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

EVENTS = frozenset({
    "token_chunk",
    "interrupt_requested",
    "generation_interrupted",
    "generation_completed",
    "session_snapshot",
    "user_message",
})

REQUIRED = {
    "token_chunk": ("session_id", "token", "sequence"),
    "interrupt_requested": ("session_id", "new_input"),
    "generation_interrupted": (
        "session_id", "message_id", "status"
    ),
    "generation_completed": ("session_id", "message_id"),
    "session_snapshot": ("session_id", "messages"),
    "user_message": ("session_id", "text"),
}


def envelope(event: str, data: dict) -> dict:
    """Crear evento estructurado sin reutilizar SSE/RFP."""
    if event not in EVENTS or not isinstance(data, dict):
        raise ValueError("Evento de chat inválido")

    if any(field not in data for field in REQUIRED[event]):
        raise ValueError("Faltan campos obligatorios")

    if (
        not isinstance(data["session_id"], str)
        or not data["session_id"].strip()
    ):
        raise ValueError("session_id inválido")

    if event == "token_chunk":
        if (
            not isinstance(data["token"], str)
            or type(data["sequence"]) is not int
            or data["sequence"] < 1
        ):
            raise ValueError("Token o secuencia inválidos")

    if event == "generation_interrupted":
        if data["status"] != "interrupted":
            raise ValueError("Estado de interrupción inválido")

    if event == "session_snapshot":
        if not isinstance(data["messages"], list):
            raise ValueError("Historial inválido")

    return {"event": event, "data": data}


@dataclass(frozen=True)
class ChatSession:
    session_id: str
    agent_id: str
    user_id: int
    client_id: str
    status: str
    created_at: str


class ChatSessionStore:
    """Sesiones SQLite con control de propiedad."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self._db() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    client_id TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK(status IN (
                            'active',
                            'interrupted',
                            'closed'
                        )),
                    created_at TEXT NOT NULL
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL
                        CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sequence INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id)
                        REFERENCES chat_sessions(session_id)
                )
            """)

    @contextmanager
    def _db(self):
        conn = sqlite3.connect(
            str(self.path),
            timeout=10
        )

        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create(
        self,
        *,
        user_id: int,
        client_id: str
    ) -> ChatSession:

        if type(user_id) is not int or user_id < 1:
            raise ValueError("user_id inválido")

        if (
            not isinstance(client_id, str)
            or not client_id.strip()
        ):
            raise ValueError("client_id obligatorio")

        session = ChatSession(
            session_id=f"chat_{uuid4().hex}",
            agent_id="first_line_cx",
            user_id=user_id,
            client_id=client_id,
            status="active",
            created_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )

        with self._db() as db:
            db.execute("""
                INSERT INTO chat_sessions (
                    session_id,
                    agent_id,
                    user_id,
                    client_id,
                    status,
                    created_at
                )
                VALUES (
                    :session_id,
                    :agent_id,
                    :user_id,
                    :client_id,
                    :status,
                    :created_at
                )
            """, asdict(session))

        return session

    def get(
        self,
        session_id: str,
        *,
        user_id: int,
        client_id: str
    ) -> ChatSession:

        with self._db() as db:
            row = db.execute("""
                SELECT *
                FROM chat_sessions
                WHERE session_id=?
                  AND user_id=?
                  AND client_id=?
            """, (
                session_id,
                user_id,
                client_id
            )).fetchone()

        if row is None:
            raise PermissionError("Sesión no disponible")

        return ChatSession(**dict(row))

    def set_status(
        self,
        session_id: str,
        *,
        user_id: int,
        client_id: str,
        status: str
    ) -> None:

        if status not in (
            "active",
            "interrupted",
            "closed"
        ):
            raise ValueError("Estado inválido")

        session = self.get(
            session_id,
            user_id=user_id,
            client_id=client_id
        )

        if (
            session.status == "closed"
            and status != "closed"
        ):
            raise ValueError(
                "No se puede reabrir una sesión cerrada"
            )

        with self._db() as db:
            db.execute("""
                UPDATE chat_sessions
                SET status=?
                WHERE session_id=?
            """, (status, session_id))

    def add_message(
        self,
        session_id: str,
        *,
        user_id: int,
        client_id: str,
        role: str,
        content: str = ""
    ) -> str:

        session = self.get(
            session_id,
            user_id=user_id,
            client_id=client_id
        )

        if session.status == "closed":
            raise ValueError("Sesión cerrada")

        if (
            role not in ("user", "assistant")
            or not isinstance(content, str)
        ):
            raise ValueError("Mensaje inválido")

        message_id = f"msg_{uuid4().hex}"

        with self._db() as db:
            db.execute("""
                INSERT INTO chat_messages (
                    message_id,
                    session_id,
                    role,
                    content,
                    status,
                    sequence,
                    created_at
                )
                VALUES (?,?,?,?,?,?,?)
            """, (
                message_id,
                session_id,
                role,
                content,
                (
                    "streaming"
                    if role == "assistant"
                    else "completed"
                ),
                0,
                datetime.now(
                    timezone.utc
                ).isoformat(),
            ))

        return message_id

    def append_token(
        self,
        message_id: str,
        *,
        session_id: str,
        user_id: int,
        client_id: str,
        token: str
    ) -> int:

        self.get(
            session_id,
            user_id=user_id,
            client_id=client_id
        )

        if not isinstance(token, str) or not token:
            raise ValueError("Token inválido")

        with self._db() as db:
            result = db.execute("""
                UPDATE chat_messages
                SET
                    content=content||?,
                    sequence=sequence+1
                WHERE message_id=?
                  AND session_id=?
                  AND role='assistant'
                  AND status='streaming'
            """, (
                token,
                message_id,
                session_id
            ))

            if result.rowcount != 1:
                raise ValueError(
                    "Generación inexistente o cerrada"
                )

            row = db.execute("""
                SELECT sequence
                FROM chat_messages
                WHERE message_id=?
            """, (message_id,)).fetchone()

        return row["sequence"]


    def replace_message_content(
        self,
        message_id: str,
        *,
        session_id: str,
        user_id: int,
        client_id: str,
        content: str,
    ) -> None:
        """Sustituir contenido provisional por resultado definitivo."""

        self.get(
            session_id,
            user_id=user_id,
            client_id=client_id,
        )

        if not isinstance(content, str):
            raise ValueError("Contenido inválido")

        with self._db() as db:
            result = db.execute(
                """
                UPDATE chat_messages
                SET content=?
                WHERE message_id=?
                  AND session_id=?
                  AND role='assistant'
                  AND status='streaming'
                """,
                (content, message_id, session_id),
            )

            if result.rowcount != 1:
                raise ValueError(
                    "Mensaje inexistente o finalizado"
                )

    def finish_message(
        self,
        message_id: str,
        *,
        session_id: str,
        user_id: int,
        client_id: str,
        status: str
    ) -> None:

        self.get(
            session_id,
            user_id=user_id,
            client_id=client_id
        )

        if status not in (
            "completed",
            "interrupted"
        ):
            raise ValueError(
                "Estado de mensaje inválido"
            )

        with self._db() as db:
            result = db.execute("""
                UPDATE chat_messages
                SET status=?
                WHERE message_id=?
                  AND session_id=?
                  AND role='assistant'
                  AND status='streaming'
            """, (
                status,
                message_id,
                session_id
            ))

            if result.rowcount != 1:
                raise ValueError(
                    "Generación inexistente o finalizada"
                )

    def snapshot(
        self,
        session_id: str,
        *,
        user_id: int,
        client_id: str
    ) -> dict:

        self.get(
            session_id,
            user_id=user_id,
            client_id=client_id
        )

        with self._db() as db:
            rows = db.execute("""
                SELECT
                    message_id,
                    role,
                    content,
                    status,
                    sequence,
                    created_at
                FROM chat_messages
                WHERE session_id=?
                ORDER BY created_at, rowid
            """, (session_id,)).fetchall()

        return envelope(
            "session_snapshot",
            {
                "session_id": session_id,
                "messages": [
                    dict(row)
                    for row in rows
                ]
            }
        )


class ChatPubSub:
    """Pub/sub en memoria para un solo proceso."""

    def __init__(self):
        self._subscribers = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        session_id: str
    ) -> asyncio.Queue:

        queue = asyncio.Queue(maxsize=128)

        async with self._lock:
            self._subscribers.setdefault(
                session_id,
                set()
            ).add(queue)

        return queue

    async def unsubscribe(
        self,
        session_id: str,
        queue: asyncio.Queue
    ) -> None:

        async with self._lock:
            listeners = self._subscribers.get(
                session_id
            )

            if listeners is not None:
                listeners.discard(queue)

                if not listeners:
                    self._subscribers.pop(
                        session_id,
                        None
                    )

    async def publish(
        self,
        session_id: str,
        event: dict
    ) -> None:

        if (
            event.get("data", {}).get("session_id")
            != session_id
        ):
            raise ValueError(
                "Canal y sesión no coinciden"
            )

        async with self._lock:
            for queue in tuple(
                self._subscribers.get(
                    session_id,
                    ()
                )
            ):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # El consumidor debe recuperar
                    # el historial con snapshot.
                    self._subscribers[
                        session_id
                    ].discard(queue)
