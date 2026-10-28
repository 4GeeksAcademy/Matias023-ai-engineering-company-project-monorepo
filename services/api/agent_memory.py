"""Memoria persistente del agente, separada del RAG y checkpoints."""

import os
import sqlite3

from agent_memory_evaluator import contains_sensitive_memory
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "agent_memory.sqlite3"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class AgentMemory:
    def __init__(self, path=DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        fd = os.open(
            self.path,
            os.O_CREAT | os.O_RDWR,
            0o600,
        )
        os.fchmod(fd, 0o600)
        os.close(fd)

        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS one_pending_proposal
                ON proposals(user_id) WHERE status = 'pending';

                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    proposal_id INTEGER NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(proposal_id) REFERENCES proposals(id)
                );
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def propose(self, user_id: int, content: str):
        if type(user_id) is not int or user_id < 1:
            raise ValueError("Invalid user")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Empty proposal")
        if len(content) > 1000:
            raise ValueError("Proposal too long")
        if contains_sensitive_memory(content):
            raise ValueError("Sensitive memory content")

        with self.connect() as db:
            try:
                cursor = db.execute(
                    """INSERT INTO proposals
                       (user_id, content, status, created_at)
                       VALUES (?, ?, 'pending', ?)""",
                    (user_id, content.strip(), utc_now()),
                )
            except sqlite3.IntegrityError:
                raise ValueError(
                    "User already has a pending proposal"
                ) from None
            return cursor.lastrowid

    def pending(self, user_id: int):
        with self.connect() as db:
            row = db.execute(
                """SELECT id, content, created_at
                   FROM proposals
                   WHERE user_id=? AND status='pending'""",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def decide(
        self,
        user_id: int,
        proposal_id: int,
        approved: bool,
        edited_content: str | None = None,
    ):
        if type(approved) is not bool:
            raise ValueError("Explicit decision required")

        if edited_content is not None:
            if not approved:
                raise ValueError("Cannot edit a rejected proposal")
            if not isinstance(edited_content, str):
                raise ValueError("Invalid edited content")
            edited_content = edited_content.strip()
            if not edited_content or len(edited_content) > 1000:
                raise ValueError("Invalid edited content")
            if contains_sensitive_memory(edited_content):
                raise ValueError("Sensitive memory content")

        with self.connect() as db:
            row = db.execute(
                """SELECT id, content FROM proposals
                   WHERE id=? AND user_id=? AND status='pending'""",
                (proposal_id, user_id),
            ).fetchone()

            if row is None:
                raise ValueError("Pending proposal not found")

            status = "approved" if approved else "rejected"
            now = utc_now()

            db.execute(
                """UPDATE proposals
                   SET status=?, decided_at=?
                   WHERE id=?""",
                (status, now, proposal_id),
            )

            if approved:
                db.execute(
                    """INSERT INTO memories
                       (user_id, content, proposal_id, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (
                        user_id,
                        edited_content
                        if edited_content is not None
                        else row["content"],
                        proposal_id,
                        now,
                    ),
                )

            return status

    def list_memories(self, user_id: int):
        with self.connect() as db:
            rows = db.execute(
                """SELECT id, content, created_at
                   FROM memories WHERE user_id=?
                   ORDER BY id""",
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]


    def list_proposals(self, user_id: int):
        """Historial de decisiones exclusivo del usuario."""
        with self.connect() as db:
            rows = db.execute(
                """SELECT
                       p.id,
                       p.content AS original_content,
                       p.status,
                       p.created_at,
                       p.decided_at,
                       m.content AS saved_content
                   FROM proposals p
                   LEFT JOIN memories m ON m.proposal_id = p.id
                   WHERE p.user_id = ?
                   ORDER BY p.id DESC""",
                (user_id,),
            ).fetchall()

            return [
                {
                    **dict(row),
                    "edited": (
                        row["saved_content"] is not None
                        and row["saved_content"] != row["original_content"]
                    ),
                }
                for row in rows
            ]


    def delete_memory(self, user_id: int, memory_id: int) -> bool:
        """Elimina un recuerdo propio sin borrar su auditoría."""
        with self.connect() as db:
            cursor = db.execute(
                """DELETE FROM memories
                   WHERE id = ? AND user_id = ?""",
                (memory_id, user_id),
            )
            return cursor.rowcount == 1


    def consolidate_memories(self, user_id: int):
        """Elimina recuerdos idénticos normalizados del mismo usuario."""
        with self.connect() as db:
            rows = db.execute(
                """SELECT id, content FROM memories
                   WHERE user_id = ? ORDER BY id""",
                (user_id,),
            ).fetchall()

            seen = set()
            duplicates = []

            for row in rows:
                normalized = " ".join(
                    row["content"].casefold().split()
                )
                if normalized in seen:
                    duplicates.append(row["id"])
                else:
                    seen.add(normalized)

            for memory_id in duplicates:
                db.execute(
                    """DELETE FROM memories
                       WHERE id = ? AND user_id = ?""",
                    (memory_id, user_id),
                )

            return {
                "removed_duplicates": len(duplicates),
                "remaining": len(rows) - len(duplicates),
            }
