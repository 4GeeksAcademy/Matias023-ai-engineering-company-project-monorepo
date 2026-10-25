"""Pruebas reproducibles de memoria del agente TrackFlow."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent_memory import AgentMemory
from agent_memory_evaluator import evaluate_memory_candidate
from main import app
from routers.agent import get_agent_runner, get_memory_store
from security import get_current_user, oauth2_scheme


@pytest.fixture
def memory(tmp_path):
    return AgentMemory(tmp_path / "memory.sqlite3")


@pytest.fixture
def client(memory):
    app.dependency_overrides[get_current_user] = (
        lambda: SimpleNamespace(id=1)
    )
    app.dependency_overrides[get_memory_store] = lambda: memory
    app.dependency_overrides[oauth2_scheme] = lambda: "jwt-test"
    app.dependency_overrides[get_agent_runner] = lambda: (
        lambda question, *, token, approved_memories=None: {
            "answer": "Respuesta de prueba",
            "abstained": False,
            "reason": "ok",
            "sources": [],
            "threshold": 0.54,
        }
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_propuesta_visible_no_guardada(client, memory):
    response = client.post(
        "/agent/query",
        json={"question": "Prefiero respuestas breves"},
    )
    assert response.status_code == 200
    proposal = response.json()["memory_proposal"]
    assert proposal["id"] == memory.pending(1)["id"]
    assert memory.list_memories(1) == []


def test_aprobacion_y_edicion(client, memory):
    proposal = memory.propose(1, "Prefiero textos largos")
    response = client.post(
        f"/agent/memory/proposals/{proposal}/decision",
        json={
            "approved": True,
            "edited_content": "Prefiero textos breves",
        },
    )
    assert response.status_code == 200
    assert memory.list_memories(1)[0]["content"] == (
        "Prefiero textos breves"
    )
    assert memory.list_proposals(1)[0]["edited"] is True


def test_rechazo_no_guarda(client, memory):
    proposal = memory.propose(1, "Prefiero tablas")
    response = client.post(
        f"/agent/memory/proposals/{proposal}/decision",
        json={"approved": False},
    )
    assert response.status_code == 200
    assert memory.list_memories(1) == []
    assert memory.list_proposals(1)[0]["status"] == "rejected"


def test_contenido_sensible_rechazado(memory):
    with pytest.raises(ValueError):
        memory.propose(1, "Mi contraseña es secreta")

    proposal = memory.propose(1, "Prefiero respuestas claras")
    with pytest.raises(ValueError):
        memory.decide(
            1, proposal, True,
            edited_content="Mi token es abc123",
        )
    assert memory.list_memories(1) == []


def test_tres_interacciones_sin_recuerdo():
    examples = [
        "¿Cuál es el estado del ticket 42?",
        "Mi contraseña es secreta",
        "Bearer abcdef123456",
    ]
    for message in examples:
        assert evaluate_memory_candidate(message) is None


def test_consolidacion_por_usuario(memory):
    for user_id, content in (
        (1, "Prefiero respuestas breves"),
        (1, " PREFIERO   RESPUESTAS BREVES "),
        (2, "Prefiero respuestas breves"),
    ):
        proposal = memory.propose(user_id, content)
        memory.decide(user_id, proposal, True)

    result = memory.consolidate_memories(1)
    assert result["removed_duplicates"] == 1
    assert len(memory.list_memories(1)) == 1
    assert len(memory.list_memories(2)) == 1


def test_query_usa_solo_memorias_aprobadas_del_usuario(memory):
    """El ejecutor recibe solo recuerdos aprobados del usuario actual."""
    captured = []
    identity = {"id": 1}

    def fake_runner(question, *, token, approved_memories=None):
        captured.append(list(approved_memories or []))
        return {
            "answer": "Respuesta de prueba",
            "abstained": False,
            "reason": "ok",
            "sources": [],
            "threshold": 0.54,
        }

    app.dependency_overrides[get_current_user] = (
        lambda: SimpleNamespace(id=identity["id"])
    )
    app.dependency_overrides[get_memory_store] = lambda: memory
    app.dependency_overrides[oauth2_scheme] = lambda: "jwt-test"
    app.dependency_overrides[get_agent_runner] = (
        lambda: fake_runner
    )

    try:
        own = memory.propose(1, "Prefiero respuestas breves")
        memory.decide(1, own, True)

        other = memory.propose(2, "Prefiero respuestas largas")
        memory.decide(2, other, True)

        pending = memory.propose(1, "Prefiero tablas")

        client = TestClient(app)
        response = client.post(
            "/agent/query",
            json={"question": "¿Qué cobertura ofrece SEUR?"},
        )
        assert response.status_code == 200, response.text
        assert captured[-1] == ["Prefiero respuestas breves"]

        identity["id"] = 2
        response = client.post(
            "/agent/query",
            json={"question": "¿Qué cobertura ofrece SEUR?"},
        )
        assert response.status_code == 200, response.text
        assert captured[-1] == ["Prefiero respuestas largas"]

        assert memory.pending(1)["id"] == pending
        print("PASS: aislamiento y consentimiento respetados")

    finally:
        app.dependency_overrides.clear()


def test_langgraph_usa_memoria_sin_alterar_fuentes():
    from agent_graph import build_agent

    prompts = []

    class Retriever:
        def retrieve(self, question, *, top_k, threshold):
            return [{
                "text": "SEUR ofrece cobertura nacional.",
                "source_document": "doc-1",
                "source_file": "cobertura.md",
                "section": "Cobertura",
                "chunk_index": 0,
                "score": 0.95,
            }]

    class Service:
        threshold = 0.54
        retriever = Retriever()

        def generator(self, prompt):
            prompts.append(prompt)
            return "SEUR ofrece cobertura nacional [1]."

        def abstain(self, reason):
            return {
                "answer": "Sin información suficiente",
                "abstained": True,
                "reason": reason,
                "sources": [],
                "threshold": self.threshold,
            }

    graph = build_agent(service=Service())
    result = graph.invoke(
        {"question": "¿Qué cobertura ofrece SEUR?"},
        config={
            "configurable": {
                "thread_id": "test-memory-langgraph"
            }
        },
        context={
            "approved_memories": [
                "El usuario prefiere respuestas breves."
            ]
        },
    )

    assert prompts
    assert "El usuario prefiere respuestas breves." in prompts[0]
    assert "Responde solo usando estos" in prompts[0]
    assert "SEUR ofrece cobertura nacional." in prompts[0]
    assert result["abstained"] is False
    assert result["sources"][0]["source_document"] == "doc-1"
