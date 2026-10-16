"""Pruebas HTTP del router RAG sin Gemini ni Qdrant."""

import pytest
from fastapi.testclient import TestClient

from main import app
from routers.rag import get_rag_service
from security import get_current_user


class FakeRAG:
    def query(self, question):
        return {
            "answer": "SEUR cubre Aragón rural [1].",
            "abstained": False,
            "reason": "ok",
            "sources": [{
                "citation": 1,
                "source_document": "carrier-coverage",
                "source_file": (
                    "trackflow-carrier-coverage.es.md"
                ),
                "section": "Cobertura",
                "chunk_index": 1,
                "score": 0.72,
            }],
            "threshold": 0.54,
        }


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = (
        lambda: {"id": 1}
    )
    app.dependency_overrides[get_rag_service] = (
        lambda: FakeRAG()
    )

    yield TestClient(app)

    app.dependency_overrides.pop(
        get_current_user, None
    )
    app.dependency_overrides.pop(
        get_rag_service, None
    )


def test_rag_query_con_fuentes(client):
    response = client.post(
        "/rag/query",
        json={
            "question": (
                "¿Qué transportista cubre Aragón rural?"
            )
        },
    )

    assert response.status_code == 200

    result = response.json()

    assert result["abstained"] is False
    assert "[1]" in result["answer"]
    assert len(result["sources"]) == 1
    assert result["sources"][0][
        "source_document"
    ] == "carrier-coverage"


def test_rag_rechaza_pregunta_vacia(client):
    response = client.post(
        "/rag/query",
        json={"question": "   "},
    )
    assert response.status_code == 422


def test_rag_rechaza_pregunta_larga(client):
    response = client.post(
        "/rag/query",
        json={"question": "x" * 1001},
    )
    assert response.status_code == 422


def test_rag_protegido_sin_sesion():
    response = TestClient(app).post(
        "/rag/query",
        json={"question": "¿Cuál es el SLA?"},
    )
    assert response.status_code in (401, 403)


def test_rag_error_externo_controlado(client):
    class BrokenRAG:
        def query(self, question):
            raise RuntimeError(
                "ERROR INTERNO DE PRUEBA"
            )

    app.dependency_overrides[get_rag_service] = (
        lambda: BrokenRAG()
    )

    response = client.post(
        "/rag/query",
        json={"question": "Consulta válida"},
    )

    assert response.status_code == 503
    assert "ERROR INTERNO" not in response.text


def test_health_anterior_conservado(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
