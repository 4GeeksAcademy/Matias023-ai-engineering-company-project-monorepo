"""Rate limiting distribuido para endpoints IA de TrackFlow."""

import os

import redis


RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])

if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end

local ttl = redis.call('TTL', KEYS[1])

if ttl < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end

return {count, ttl}
"""


class AIRateLimitUnavailable(Exception):
    """Redis no está disponible para verificar el límite."""


class AIRateLimiter:
    def __init__(self, client=None, limit=None, window=None):
        self.limit = int(
            limit if limit is not None
            else os.getenv("AI_RATE_LIMIT_REQUESTS", "10")
        )
        self.window = int(
            window if window is not None
            else os.getenv("AI_RATE_LIMIT_WINDOW", "60")
        )

        if self.limit <= 0 or self.window <= 0:
            raise ValueError("Rate limit y ventana deben ser positivos")

        self.client = client if client is not None else redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )

    def check(self, user_id: int, endpoint: str = "rag"):
        """Devuelve (permitido, segundos_para_reintentar)."""

        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise ValueError("ID de usuario inválido")

        if endpoint != "rag":
            raise ValueError("Endpoint no autorizado para este limitador")

        key = f"trackflow:ai:rate:{endpoint}:user:{user_id}"

        try:
            count, ttl = self.client.eval(
                RATE_LIMIT_SCRIPT,
                1,
                key,
                self.window,
            )
        except redis.RedisError as exc:
            raise AIRateLimitUnavailable(
                "No se pudo verificar el límite de solicitudes"
            ) from exc

        allowed = int(count) <= self.limit
        retry_after = max(int(ttl), 1)

        return allowed, retry_after
