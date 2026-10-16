"""Prueba de recuperación entre conexiones SQLite."""

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/api"))
sys.path.insert(0, str(ROOT / "scripts/rag"))

from agent_persistence import persistent_agent
from generate import ABSTENTION, RAGService


class FakeRetriever:
    def __init__(self):
        self.calls = 0

    def retrieve(self, question, **kwargs):
        self.calls += 1
        return []


class FakeGenerator:
    def __init__(self):
        self.calls = 0

    def __call__(self, prompt):
        self.calls += 1
        raise AssertionError("No debe ejecutarse Gemini")


def test_checkpoint_persiste_tras_reabrir(tmp_path):
    database = tmp_path / "checkpoints.sqlite3"
    retriever = FakeRetriever()
    generator = FakeGenerator()

    service = RAGService(
        retriever=retriever,
        generator=generator,
    )

    config = {
        "configurable": {
            "thread_id": str(uuid4()),
        }
    }

    with persistent_agent(service, database) as graph:
        result = graph.invoke(
            {"question": "Consulta sin evidencia"},
            config,
        )
        assert result["answer"] == ABSTENTION
        assert result["abstained"] is True
        assert retriever.calls == 1
        assert generator.calls == 0
        assert graph.get_state(config).values["reason"] == (
            "sin_fragmentos_sobre_umbral"
        )

    assert database.is_file()

    with persistent_agent(service, database) as reopened:
        snapshot = reopened.get_state(config)
        assert snapshot.values["answer"] == ABSTENTION
        assert snapshot.values["abstained"] is True
        assert snapshot.values["reason"] == (
            "sin_fragmentos_sobre_umbral"
        )
        assert snapshot.next == ()
        assert list(reopened.get_state_history(config))

    assert retriever.calls == 1
    assert generator.calls == 0


def test_reanudacion_desde_interrupcion(tmp_path):
    """Reanuda generate tras cerrar y reabrir SQLite."""

    database = tmp_path / "resume.sqlite3"

    hit = {
        "text": "SEUR: mejor cobertura en Aragón rural.",
        "source_document": "carrier-coverage",
        "source_file": "trackflow-carrier-coverage.es.md",
        "section": "Cobertura",
        "chunk_index": 1,
        "score": 0.80,
    }

    class Retriever:
        def __init__(self):
            self.calls = 0

        def retrieve(self, question, **kwargs):
            self.calls += 1
            return [hit]

    class Generator:
        def __init__(self):
            self.calls = 0

        def __call__(self, prompt):
            self.calls += 1
            return (
                "SEUR ofrece mejor cobertura "
                "en Aragón rural [1]."
            )

    retriever = Retriever()
    generator = Generator()

    service = RAGService(
        retriever=retriever,
        generator=generator,
    )

    config = {
        "configurable": {
            "thread_id": str(uuid4()),
        }
    }

    with persistent_agent(service, database) as graph:
        graph.invoke(
            {"question": "¿Qué transportista cubre Aragón rural?"},
            config=config,
            interrupt_before=["generate"],
        )

        snapshot = graph.get_state(config)

        assert snapshot.next == ("generate",)
        assert retriever.calls == 1
        assert generator.calls == 0

    with persistent_agent(service, database) as reopened:
        snapshot = reopened.get_state(config)
        assert snapshot.next == ("generate",)

        result = reopened.invoke(None, config=config)

        assert result["abstained"] is False
        assert result["reason"] == "ok"
        assert reopened.get_state(config).next == ()

    assert retriever.calls == 1
    assert generator.calls == 1



def test_checkpoint_sqlite_permisos_privados(tmp_path):
    """El archivo SQLite solo puede ser leído por su propietario."""
    import stat

    database = tmp_path / "secure.sqlite3"

    with persistent_agent(database=database) as graph:
        assert graph is not None

    assert database.is_file()
    mode = stat.S_IMODE(database.stat().st_mode)
    assert mode == 0o600, f"Permisos inseguros: {oct(mode)}"
