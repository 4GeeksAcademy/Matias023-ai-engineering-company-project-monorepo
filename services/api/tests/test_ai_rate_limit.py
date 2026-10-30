"""Pruebas del rate limiting IA sin Redis ni Gemini reales."""

from collections import defaultdict
from types import SimpleNamespace

import pytest
import redis
from fastapi.testclient import TestClient

from ai_rate_limit import (
    AIRateLimiter,
    AIRateLimitUnavailable,
    RATE_LIMIT_SCRIPT,
)
from main import app
from routers.rag import get_ai_rate_limiter, get_rag_service
from security import get_current_user


class FakeRedis:
    """Simula el resultado atomico de Redis EVAL."""

    def __init__(self):
        self.counts = defaultdict(int)
        self.calls = []

    def eval(self, script, numkeys, key, window):
        assert script == RATE_LIMIT_SCRIPT
        assert numkeys == 1
        self.calls.append((key, window))
        self.counts[key] += 1
        return [self.counts[key], window]


class BrokenRedis:
    def eval(self, *args):
        raise redis.ConnectionError("Redis unavailable")


class SpyRAG:
    def __init__(self):
        self.calls = 0

    def query(self, question):
        self.calls += 1
        return {
            "answer": "Respuesta controlada",
            "abstained": False,
            "reason": "ok",
            "sources": [],
            "threshold": 0.54,
        }


@pytest.fixture
def environment():
    backend = FakeRedis()
    limiter = AIRateLimiter(client=backend, limit=2, window=60)
    rag = SpyRAG()
    identity = {"id": 1}

    app.dependency_overrides[get_current_user] = (
        lambda: SimpleNamespace(id=identity["id"])
    )
    app.dependency_overrides[get_ai_rate_limiter] = (
        lambda: limiter
    )
    app.dependency_overrides[get_rag_service] = (
        lambda: rag
    )

    try:
        with TestClient(app) as client:
            yield client, backend, rag, identity
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_ai_rate_limiter, None)
        app.dependency_overrides.pop(get_rag_service, None)


def test_solicitudes_permitidas(environment):
    client, backend, rag, _ = environment

    for _ in range(2):
        response = client.post(
            "/rag/query",
            json={"question": "Consulta valida"},
        )
        assert response.status_code == 200

    assert rag.calls == 2
    assert len(backend.calls) == 2


def test_http_429_y_modelo_no_invocado(environment):
    client, _, rag, _ = environment

    for _ in range(2):
        assert client.post(
            "/rag/query",
            json={"question": "Consulta valida"},
        ).status_code == 200

    response = client.post(
        "/rag/query",
        json={"question": "Consulta bloqueada"},
    )

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert rag.calls == 2


def test_usuarios_con_cuotas_independientes(environment):
    client, backend, rag, identity = environment

    identity["id"] = 1
    for _ in range(2):
        assert client.post(
            "/rag/query",
            json={"question": "Usuario uno"},
        ).status_code == 200

    identity["id"] = 2
    response = client.post(
        "/rag/query",
        json={"question": "Usuario dos"},
    )

    assert response.status_code == 200
    assert rag.calls == 3
    assert len(backend.counts) == 2


def test_http_503_si_redis_falla(environment):
    client, _, rag, _ = environment

    app.dependency_overrides[get_ai_rate_limiter] = (
        lambda: AIRateLimiter(
            client=BrokenRedis(),
            limit=2,
            window=60,
        )
    )

    response = client.post(
        "/rag/query",
        json={"question": "Consulta valida"},
    )

    assert response.status_code == 503
    assert rag.calls == 0


def test_error_redis_se_traduce_a_excepcion_controlada():
    limiter = AIRateLimiter(
        client=BrokenRedis(),
        limit=2,
        window=60,
    )

    with pytest.raises(AIRateLimitUnavailable):
        limiter.check(user_id=1)


def test_clave_no_contiene_credenciales():
    backend = FakeRedis()
    limiter = AIRateLimiter(
        client=backend,
        limit=2,
        window=60,
    )

    limiter.check(user_id=123)

    key, window = backend.calls[0]

    assert key == "trackflow:ai:rate:rag:user:123"
    assert window == 60
    assert "@" not in key
    assert "Bearer" not in key
