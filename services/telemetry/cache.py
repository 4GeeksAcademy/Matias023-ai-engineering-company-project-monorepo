"""In-memory TTL cache for telemetry report metrics.

Key design points:
    * Simple dict-based cache with TTL expiry.
    * Thread-safe via a threading.Lock (sufficient for FastAPI's multi-threaded
      uvicorn workers without a dedicated caching service).
    * Cache key is (start_date.isoformat(), end_date.isoformat()).
    * TTL = 60 seconds (configurable via keyword argument).
    * Avoids recomputing metrics when the same date window is requested within
      the TTL window.
    * Manually invalidation is NOT needed — the cache auto-expires.
"""

from __future__ import annotations

import threading
import time
from datetime import date
from typing import Any


class ReportCache:
    """Thread-safe in-memory cache for telemetry report results.

    Usage::

        cache = ReportCache(default_ttl=60)

        # On cache miss / expiry:
        result = cache.get_or_compute(start, end, compute_fn)

        # The compute_fn is called only when the cache misses or TTL expires.
    """

    def __init__(self, default_ttl: float = 60.0) -> None:
        """Initialize an empty cache.

        Args:
            default_ttl: Default time-to-live in seconds (default 60).
        """
        self._default_ttl = default_ttl
        self._data: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._lock = threading.Lock()

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    def get(
        self, start_date: date, end_date: date
    ) -> list[dict[str, Any]] | None:
        """Return the cached result for *(start_date, end_date)* if fresh.

        Returns ``None`` when the key is missing or the entry has expired.
        """
        key = self._make_key(start_date, end_date)
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            stored_at, result = entry
            if self._is_expired(stored_at):
                del self._data[key]
                return None
            return result

    def set(
        self, start_date: date, end_date: date, result: list[dict[str, Any]]
    ) -> None:
        """Store *result* under the key *(start_date, end_date)*.

        The entry's TTL begins counting from the moment this method is
        called (i.e. ``time.monotonic()`` is captured on set).
        """
        key = self._make_key(start_date, end_date)
        with self._lock:
            self._data[key] = (time.monotonic(), result)

    def get_or_compute(
        self,
        start_date: date,
        end_date: date,
        compute_fn: callable,
    ) -> list[dict[str, Any]]:
        """Return a cached result or compute and cache it.

        ``compute_fn`` is a zero-argument callable invoked only on a cache
        miss or when the cached entry has expired.  The result of
        ``compute_fn`` is stored in the cache and also returned.

        Typical usage::

            result = cache.get_or_compute(start, end, lambda: my_fn(a, b))
        """
        cached = self.get(start_date, end_date)
        if cached is not None:
            return cached

        # Cache miss or expired — compute.
        result = compute_fn()
        self.set(start_date, end_date, result)
        return result

    def invalidate(self, start_date: date, end_date: date) -> None:
        """Explicitly remove a cache entry (useful in tests)."""
        key = self._make_key(start_date, end_date)
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        """Remove all cache entries."""
        with self._lock:
            self._data.clear()

    # ──────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────

    @staticmethod
    def _make_key(start_date: date, end_date: date) -> str:
        return f"{start_date.isoformat()}|{end_date.isoformat()}"

    def _is_expired(self, stored_at: float) -> bool:
        return (time.monotonic() - stored_at) > self._default_ttl


# Module-level singleton — imported and used by the telemetry router.
# Using a module-level instance means the cache is shared across requests.
report_cache = ReportCache(default_ttl=60.0)