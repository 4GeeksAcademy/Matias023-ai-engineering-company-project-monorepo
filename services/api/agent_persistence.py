"""Persistencia local del agente TrackFlow."""

import os
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from agent_graph import build_agent

DATABASE = Path(__file__).resolve().parent / "agent_checkpoints.sqlite3"


@contextmanager
def persistent_agent(service=None, database=DATABASE):
    """Abre grafo y SQLite; cierra conexión al salir."""
    os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

    path = Path(database)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Restringir permisos al propietario desde la creación.
    # También protege una base local preexistente.
    fd = os.open(
        path,
        os.O_CREAT | os.O_RDWR,
        0o600,
    )
    try:
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)

    with SqliteSaver.from_conn_string(str(path)) as saver:
        graph = build_agent(
            service=service,
            checkpointer=saver,
        )
        yield graph
