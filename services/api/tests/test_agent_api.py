"""Pruebas HTTP del agente sin servicios externos."""

import pytest
from fastapi.testclient import TestClient

from main import app
from routers.agent import get_agent_runner
from security import get_current_user


def fake_result(question):
    return {
        "answer": "SEUR cubre Aragón rural [1].",
        "abstained": False,
        "reason": "ok",
        "sources": [{
            "citation": 1,
            "source_document": "carrier-coverage",
            "source_file": "trackflow-carrier-coverage.es.md",
            "section": "Cobertura",
            "chunk_index": 1,
            "score": 0.8,
        }],
        "threshold": 0.54,
    }


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = (
        lambda: {"id": 1}
    )
    app.dependency_overrides[get_agent_runner] = (
        lambda: fake_result
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(
            get_current_user, None
        )
        app.dependency_overrides.pop(
            get_agent_runner, None
        )


def test_agent_query_con_fuentes(client):
    response = client.post(
        "/agent/query",
        json={"question": "¿Qué cobertura ofrece SEUR?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["abstained"] is False
    assert len(data["sources"]) == 1
    assert data["sources"][0]["citation"] == 1


def test_agent_pregunta_vacia(client):
    response = client.post(
        "/agent/query",
        json={"question": "   "},
    )
    assert response.status_code == 422


def test_agent_pregunta_larga(client):
    response = client.post(
        "/agent/query",
        json={"question": "x" * 1001},
    )
    assert response.status_code == 422


def test_agent_requiere_autenticacion():
    response = TestClient(app).post(
        "/agent/query",
        json={"question": "¿Cuál es el SLA?"},
    )
    assert response.status_code in (401, 403)


def test_agent_error_controlado(client):
    def broken_runner(question):
        raise RuntimeError("SECRETO INTERNO DE PRUEBA")

    app.dependency_overrides[get_agent_runner] = (
        lambda: broken_runner
    )
    response = client.post(
        "/agent/query",
        json={"question": "Consulta válida"},
    )
    assert response.status_code == 503
    assert "SECRETO INTERNO" not in response.text


def test_agent_conserva_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
