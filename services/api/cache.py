"""
TTL Cache — in-process, thread-safe, server-side response cache.

Architecture
------------
A single ``TTLCache`` instance (``_CACHE``) is shared across all routers.
Operations acquire a reentrant lock so they are safe even when FastAPI
workers run handler code in thread-pool threads (e.g. the default
ThreadPoolExecutor for sync endpoints).

Key design
----------
* Keys are plain strings constructed deterministically from the endpoint
  namespace and all request-affecting parameters.
* TTL expiry uses ``time.monotonic()`` so it is immune to system clock
  adjustments.
* Mutable values (lists, dicts) are deep-copied on retrieval to prevent
  accidental in-place mutation from altering cached state.
* Namespace (prefix) invalidation makes it cheap to wipe all keys related
  to a resource after a mutation.

Thread safety
-------------
``threading.RLock`` (reentrant) protects internal dict operations.
Reentrancy allows cache operations to be composed without deadlock.

Usage
-----
    from cache import cache

    # Inside a FastAPI handler:
    data = cache.get("incidents:summary")
    if data is None:
        data = compute_expensive_result()
        cache.set("incidents:summary", data, ttl=30)
    return data

    # After a mutation:
    cache.invalidate_prefix("incidents:")
"""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Hashable
from typing import Any


# ---------------------------------------------------------------------------
# Constants — centralised TTL values
# ---------------------------------------------------------------------------
# Chosen based on repository mutation frequency (Phase 1 evidence):
#   * Incidents summary aggregates 4 dimensions across all incidents;
#     status transitions happen infrequently so 20 s is a safe balance.
#   * Supplier list/detail changes even less often (manual updates, rare
#     creation); 60 s reflects the low mutation rate and the fact that
#     supplier data is reference data, not real-time operational data.

INCIDENT_SUMMARY_TTL_SECONDS: int = 20
SUPPLIER_LIST_TTL_SECONDS: int = 60
SUPPLIER_DETAIL_TTL_SECONDS: int = 60

# Cache namespace prefixes — used for invalidation
INCIDENT_CACHE_NAMESPACE: str = "incidents:"
SUPPLIER_CACHE_NAMESPACE: str = "suppliers:"


# ---------------------------------------------------------------------------
# Internal entry
# ---------------------------------------------------------------------------


class _CacheEntry:
    """An entry in the cache with a monotonic expiry timestamp."""

    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, expires_at: float) -> None:
        self.value = value
        self.expires_at = expires_at

    def is_expired(self, now: float | None = None) -> bool:
        if now is None:
            now = time.monotonic()
        return now >= self.expires_at


# ---------------------------------------------------------------------------
# Public cache singleton
# ---------------------------------------------------------------------------


class TTLCache:
    """Thread-safe in-process TTL cache.

    Parameters
    ----------
    default_ttl :
        Fallback TTL (seconds) when ``set()`` is called without an explicit
        ``ttl``.  ``0`` means no expiry (use with caution).
    """

    def __init__(self, default_ttl: float = 0) -> None:
        self._default_ttl = default_ttl
        self._data: dict[str, _CacheEntry] = {}
        self._lock = threading.RLock()

        # Stats counters — NOT reset by clear() so tests can observe totals.
        self._stats_hits = 0
        self._stats_misses = 0
        self._stats_sets = 0
        self._stats_invalidations = 0

    # -- public API --------------------------------------------------------

    def get(self, key: str) -> Any | None:
        """Return the cached value for *key*, or *None* if missing/expired.

        The returned value is a **deep copy** of the stored object to
        prevent accidental mutation of cached state.
        """
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self._stats_misses += 1
                return None

            if entry.is_expired():
                del self._data[key]
                self._stats_misses += 1
                return None

            self._stats_hits += 1
            return copy.deepcopy(entry.value)

    def set(
        self,
        key: str,
        value: Hashable | list | dict,
        ttl: float | None = None,
    ) -> None:
        """Store *value* under *key* with an optional *ttl* (seconds).

        If *ttl* is *None*, the instance ``default_ttl`` is used.
        A *ttl* of ``0`` means the entry never expires.
        """
        if ttl is None:
            ttl = self._default_ttl

        expires_at = (time.monotonic() + ttl) if ttl > 0 else float("inf")

        with self._lock:
            self._data[key] = _CacheEntry(copy.deepcopy(value), expires_at)
            self._stats_sets += 1

    def delete(self, key: str) -> bool:
        """Remove *key* from the cache.  Returns *True* if it existed."""
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._stats_invalidations += 1
                return True
            return False

    def invalidate_prefix(self, prefix: str) -> int:
        """Remove all keys starting with *prefix*.

        Returns the number of entries removed.  This is the primary
        invalidation mechanism for namespaced cache keys.
        """
        count = 0
        with self._lock:
            keys_to_remove = [k for k in self._data if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._data[k]
                count += 1
            if count:
                self._stats_invalidations += count
        return count

    def clear(self) -> None:
        """Remove all entries from the cache.

        Does **not** reset stats counters so that tests can still read
        cumulative hit/miss/set/invalidation totals.
        """
        with self._lock:
            self._data.clear()

    def close(self) -> None:
        """Release resources (no-op, provided for fixture convenience)."""
        self.clear()

    # -- introspection (testing / diagnostics) -----------------------------

    @property
    def stats(self) -> dict[str, int]:
        """Return a snapshot of cumulative cache statistics."""
        with self._lock:
            return {
                "hits": self._stats_hits,
                "misses": self._stats_misses,
                "sets": self._stats_sets,
                "invalidations": self._stats_invalidations,
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def __contains__(self, key: str) -> bool:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._data[key]
                return False
            return True


# ---------------------------------------------------------------------------
# Module-level singleton — imported by routers
# ---------------------------------------------------------------------------

cache = TTLCache(default_ttl=0)  # no default expiry; callers must supply TTL