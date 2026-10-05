"""Unit tests for the TTLCache module.

These tests exercise the cache directly without any FastAPI machinery.
"""

from __future__ import annotations

import time

import pytest

from cache import TTLCache


@pytest.fixture
def cache() -> TTLCache:
    """Fresh cache instance per test."""
    c = TTLCache(default_ttl=0)
    yield c
    c.close()


# ══════════════════════════════════════════════
# Basic get/set
# ══════════════════════════════════════════════


class TestBasicOps:
    def test_miss_before_set(self, cache: TTLCache):
        assert cache.get("nonexistent") is None

    def test_hit_after_set(self, cache: TTLCache):
        cache.set("foo", "bar", ttl=60)
        assert cache.get("foo") == "bar"

    def test_hit_with_integer(self, cache: TTLCache):
        cache.set("count", 42, ttl=60)
        assert cache.get("count") == 42

    def test_hit_with_list(self, cache: TTLCache):
        data = [1, 2, 3]
        cache.set("list", data, ttl=60)
        assert cache.get("list") == [1, 2, 3]

    def test_hit_with_dict(self, cache: TTLCache):
        data = {"key": "value", "nested": {"a": 1}}
        cache.set("dict", data, ttl=60)
        assert cache.get("dict") == data

    def test_hit_with_none_value(self, cache: TTLCache):
        cache.set("null", None, ttl=60)
        # get returns None for both miss and None-value; use __contains__
        assert "null" in cache


# ══════════════════════════════════════════════
# TTL expiration
# ══════════════════════════════════════════════


class TestTTLExpiry:
    def test_expires_after_ttl(self, cache: TTLCache):
        cache.set("ephemeral", "value", ttl=0.05)
        assert cache.get("ephemeral") == "value"  # warm
        time.sleep(0.06)
        assert cache.get("ephemeral") is None  # expired

    def test_zero_ttl_never_expires(self, cache: TTLCache):
        cache.set("forever", "immutable", ttl=0)
        assert cache.get("forever") == "immutable"
        # 0 → float("inf") internally
        entry = cache._data["forever"]
        assert entry.expires_at == float("inf")

    def test_get_cleans_expired_entry(self, cache: TTLCache):
        cache.set("goner", "bye", ttl=0.02)
        time.sleep(0.03)
        _ = cache.get("goner")  # triggers expiry check
        assert "goner" not in cache


# ══════════════════════════════════════════════
# Delete
# ══════════════════════════════════════════════


class TestDelete:
    def test_delete_existing(self, cache: TTLCache):
        cache.set("del_me", "value", ttl=60)
        assert cache.delete("del_me") is True
        assert cache.get("del_me") is None

    def test_delete_nonexistent(self, cache: TTLCache):
        assert cache.delete("ghost") is False

    def test_delete_free_memory(self, cache: TTLCache):
        cache.set("a", 1, ttl=60)
        cache.set("b", 2, ttl=60)
        cache.delete("a")
        assert len(cache) == 1


# ══════════════════════════════════════════════
# Namespace invalidation
# ══════════════════════════════════════════════


class TestInvalidatePrefix:
    def test_invalidate_prefix_removes_matching(self, cache: TTLCache):
        cache.set("incidents:summary", "a", ttl=60)
        cache.set("incidents:list", "b", ttl=60)
        cache.set("suppliers:list", "c", ttl=60)

        count = cache.invalidate_prefix("incidents:")
        assert count == 2
        assert cache.get("incidents:summary") is None
        assert cache.get("incidents:list") is None
        assert cache.get("suppliers:list") == "c"

    def test_invalidate_prefix_no_match(self, cache: TTLCache):
        cache.set("only:key", "v", ttl=60)
        count = cache.invalidate_prefix("nomatch:")
        assert count == 0
        assert cache.get("only:key") == "v"

    def test_invalidate_prefix_after_mutation(self, cache: TTLCache):
        """Simulate: set → invalidate → get should miss."""
        cache.set("incidents:summary", "stale", ttl=60)
        cache.invalidate_prefix("incidents:")
        assert cache.get("incidents:summary") is None


# ══════════════════════════════════════════════
# Clear / reset
# ══════════════════════════════════════════════


class TestClear:
    def test_clear_empties_cache(self, cache: TTLCache):
        cache.set("keep", 1, ttl=60)
        cache.set("also_keep", 2, ttl=60)
        cache.clear()
        assert len(cache) == 0
        assert cache.get("keep") is None

    def test_clear_resets_for_next_set(self, cache: TTLCache):
        cache.set("temp", "v1", ttl=60)
        cache.clear()
        cache.set("temp", "v2", ttl=60)
        assert cache.get("temp") == "v2"


# ══════════════════════════════════════════════
# Deep-copy safety
# ══════════════════════════════════════════════


class TestDeepCopySafety:
    def test_mutation_does_not_affect_cache(self, cache: TTLCache):
        original = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        cache.set("users", original, ttl=60)

        retrieved = cache.get("users")
        assert retrieved is not None
        retrieved.append({"id": 3, "name": "Eve"})

        # Cache should still have the original list
        second = cache.get("users")
        assert second is not None
        assert len(second) == 2

    def test_in_place_dict_mutation(self, cache: TTLCache):
        original = {"count": 5}
        cache.set("stats", original, ttl=60)

        retrieved = cache.get("stats")
        assert retrieved is not None
        retrieved["count"] = 999

        second = cache.get("stats")
        assert second is not None
        assert second["count"] == 5


# ══════════════════════════════════════════════
# Stats
# ══════════════════════════════════════════════


class TestStats:
    def test_initial_stats_are_zero(self, cache: TTLCache):
        stats = cache.stats
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["sets"] == 0
        assert stats["invalidations"] == 0

    def test_hit_count(self, cache: TTLCache):
        cache.set("x", 1, ttl=60)
        cache.get("x")
        assert cache.stats["hits"] == 1

    def test_miss_count(self, cache: TTLCache):
        cache.get("no_such_key")
        assert cache.stats["misses"] == 1

    def test_miss_on_expired(self, cache: TTLCache):
        cache.set("tmp", "v", ttl=0.02)
        time.sleep(0.03)
        cache.get("tmp")  # miss (expired)
        assert cache.stats["misses"] == 1

    def test_set_count(self, cache: TTLCache):
        cache.set("a", 1, ttl=60)
        cache.set("b", 2, ttl=60)
        assert cache.stats["sets"] == 2

    def test_invalidation_count(self, cache: TTLCache):
        cache.set("inc:a", 1, ttl=60)
        cache.set("inc:b", 2, ttl=60)
        cache.invalidate_prefix("inc:")
        assert cache.stats["invalidations"] == 2

    def test_clear_does_not_reset_stats(self, cache: TTLCache):
        cache.set("x", 1, ttl=60)
        cache.get("x")  # hit
        cache.get("missing")  # miss
        cache.clear()
        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["sets"] == 1


# ══════════════════════════════════════════════
# Thread safety (smoke)
# ══════════════════════════════════════════════


class TestThreadSafety:
    def test_concurrent_get_set(self, cache: TTLCache):
        """Smoke test: concurrent access should not crash."""

        import concurrent.futures

        def worker(n: int):
            key = f"thread:{n}"
            cache.set(key, n, ttl=5)
            return cache.get(key)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(worker, range(20)))

        assert results == list(range(20))


# ══════════════════════════════════════════════
# Key methods
# ══════════════════════════════════════════════


class TestContains:
    def test_contains_miss(self, cache: TTLCache):
        assert ("ghost" in cache) is False

    def test_contains_hit(self, cache: TTLCache):
        cache.set("present", 42, ttl=60)
        assert ("present" in cache) is True

    def test_contains_expired(self, cache: TTLCache):
        cache.set("goner", "x", ttl=0.02)
        time.sleep(0.03)
        assert ("goner" in cache) is False