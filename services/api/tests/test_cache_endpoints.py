"""Integration tests for cache behaviour through FastAPI endpoints.

These tests verify that:
  1. A cold request (cache miss) returns the correct result.
  2. A repeated request (cache hit) returns the same data without
     hitting the underlying store.
  3. Mutations invalidate the relevant cache namespace.
  4. Different query-parameter combinations produce distinct keys.
  5. Auth always executes before cache (no bypass).
  6. TTL expiration is verified via the cache module directly.

TTL expiration is tested thoroughly in ``test_cache_unit.py``; endpoint-level
tests focus on hit/miss/invalidation semantics.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from tinydb import TinyDB

from main import app


# Router modules — imported so we can monkeypatch their table references
import routers.suppliers as suppliers_router_module
import routers.incidents as incidents_router_module
import routers.auth as auth_router_module
import routers.users as users_router_module
import seed as seed_module
import security as security_module
import cache as cache_module


# ══════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear the module-level cache singleton before each test."""
    cache_module.cache.clear()
    yield


def _make_authed_client(
    tmp_path: Any, monkeypatch: Any
) -> tuple[TestClient, dict, Any, Any, TinyDB]:
    """Create a TestClient with seeded data and a valid auth token."""
    test_db = TinyDB(tmp_path / "test-cache-db.json")
    test_suppliers_table = test_db.table("suppliers")
    test_users_table = test_db.table("users")
    test_profiles_table = test_db.table("profiles")
    test_incidents_table = test_db.table("incidents")

    # Patch suppliers
    monkeypatch.setattr(
        suppliers_router_module, "suppliers_table", test_suppliers_table
    )
    monkeypatch.setattr(seed_module, "suppliers_table", test_suppliers_table)

    # Patch incidents
    monkeypatch.setattr(
        incidents_router_module, "incidents_table", test_incidents_table
    )

    # Patch users + auth + security
    monkeypatch.setattr(users_router_module, "users_table", test_users_table)
    monkeypatch.setattr(users_router_module, "profiles_table", test_profiles_table)
    monkeypatch.setattr(auth_router_module, "users_table", test_users_table)
    monkeypatch.setattr(security_module, "users_table", test_users_table)

    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-cache-tests")

    # Seed 15 suppliers
    seed_module.main()

    # Create a test user
    client = TestClient(app)
    client.post(
        "/users",
        json={
            "email": "cache-tester@example.com",
            "password": "cachepass123",
        },
    )

    login_response = client.post(
        "/auth/login",
        json={
            "email": "cache-tester@example.com",
            "password": "cachepass123",
        },
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    return client, headers, test_incidents_table, test_suppliers_table, test_db


@pytest.fixture
def cache_env(tmp_path, monkeypatch):
    """Standard fixture: returns (client, headers, incidents_table, suppliers_table)."""
    client, headers, inc_table, sup_table, db = _make_authed_client(
        tmp_path, monkeypatch
    )
    yield client, headers, inc_table, sup_table
    db.close()


# ══════════════════════════════════════════════
# Incident summary cache tests
# ══════════════════════════════════════════════


class TestIncidentSummaryCache:
    """Verify GET /incidents/summary caching."""

    def test_cold_miss_then_hit(self, cache_env):
        client, headers, inc_table, _ = cache_env
        url = "/incidents/summary"

        cold = client.get(url, headers=headers)
        assert cold.status_code == 200
        hits_before = cache_module.cache.stats["hits"]

        warm = client.get(url, headers=headers)
        assert warm.status_code == 200
        assert warm.json() == cold.json()
        assert cache_module.cache.stats["hits"] == hits_before + 1

    def test_create_incident_invalidates_summary(self, cache_env):
        client, headers, inc_table, _ = cache_env

        client.get("/incidents/summary", headers=headers)
        hits_after_warm = cache_module.cache.stats["hits"]

        client.post(
            "/incidents",
            json={
                "title": "Test incident",
                "description": "Created for invalidation test",
                "category": "lost_parcel",
                "origin": "customer",
                "branch": "la_office",
            },
            headers=headers,
        )

        cold_after = client.get("/incidents/summary", headers=headers)
        assert cold_after.status_code == 200
        # hits should NOT have increased from warm — it was a miss
        assert cache_module.cache.stats["hits"] == hits_after_warm

    def test_status_change_invalidates_summary(self, cache_env):
        client, headers, inc_table, _ = cache_env

        create_resp = client.post(
            "/incidents",
            json={
                "title": "Change me",
                "description": "Will change status",
                "category": "lost_parcel",
                "origin": "customer",
                "branch": "la_office",
            },
            headers=headers,
        )
        inc_id = create_resp.json()["id"]

        client.get("/incidents/summary", headers=headers)
        hits_after_warm = cache_module.cache.stats["hits"]

        client.patch(
            f"/incidents/{inc_id}/status",
            json={"status": "in_progress"},
            headers=headers,
        )

        after = client.get("/incidents/summary", headers=headers)
        assert after.status_code == 200
        assert cache_module.cache.stats["hits"] == hits_after_warm

    def test_summary_still_requires_auth(self, cache_env):
        """Auth must still execute on cache hit."""
        client, headers, _, _ = cache_env

        client.get("/incidents/summary", headers=headers)
        noauth = client.get("/incidents/summary")
        assert noauth.status_code == 401


# ══════════════════════════════════════════════
# Supplier list cache tests
# ══════════════════════════════════════════════


class TestSupplierListCache:
    """Verify GET /suppliers caching."""

    def test_cold_miss_then_hit(self, cache_env):
        client, headers, _, _ = cache_env

        cold = client.get("/suppliers", headers=headers)
        assert cold.status_code == 200
        assert len(cold.json()) == 15

        misses_after_cold = cache_module.cache.stats["misses"]
        hits_after_cold = cache_module.cache.stats["hits"]

        warm = client.get("/suppliers", headers=headers)
        assert warm.status_code == 200
        assert warm.json() == cold.json()
        assert cache_module.cache.stats["hits"] == hits_after_cold + 1
        assert cache_module.cache.stats["misses"] == misses_after_cold

    def test_different_filters_different_keys(self, cache_env):
        client, headers, _, _ = cache_env

        usa = client.get("/suppliers", params={"country": "USA"}, headers=headers)
        assert usa.status_code == 200

        spain = client.get("/suppliers", params={"country": "Spain"}, headers=headers)
        assert spain.status_code == 200

        usa_again = client.get(
            "/suppliers", params={"country": "USA"}, headers=headers
        )
        assert usa_again.json() == usa.json()

        spain_again = client.get(
            "/suppliers", params={"country": "Spain"}, headers=headers
        )
        assert spain_again.json() == spain.json()

    def test_create_supplier_invalidates_list(self, cache_env):
        client, headers, _, _ = cache_env

        client.get("/suppliers", headers=headers)
        hits_after_warm = cache_module.cache.stats["hits"]

        client.post(
            "/suppliers",
            json={
                "name": "New Carrier",
                "country": "USA",
                "categories": ["carrier_last_mile"],
                "rate_per_shipment": 10.0,
                "currency": "USD",
                "status": "active",
            },
            headers=headers,
        )

        after = client.get("/suppliers", headers=headers)
        assert after.status_code == 200
        assert len(after.json()) == 16
        assert cache_module.cache.stats["hits"] == hits_after_warm

    def test_rate_update_invalidates_list(self, cache_env):
        client, headers, _, _ = cache_env

        client.get("/suppliers", headers=headers)
        hits_after_warm = cache_module.cache.stats["hits"]

        client.patch(
            "/suppliers/1/rate",
            json={"rate_per_shipment": 99.0},
            headers=headers,
        )

        after = client.get("/suppliers", headers=headers)
        assert after.status_code == 200
        assert cache_module.cache.stats["hits"] == hits_after_warm

    def test_status_update_invalidates_list(self, cache_env):
        client, headers, _, _ = cache_env

        client.get("/suppliers", headers=headers)
        hits_after_warm = cache_module.cache.stats["hits"]

        client.patch(
            "/suppliers/1/status",
            json={"status": "suspended"},
            headers=headers,
        )

        after = client.get("/suppliers", headers=headers)
        assert after.status_code == 200
        assert cache_module.cache.stats["hits"] == hits_after_warm

    def test_delete_supplier_invalidates_list(self, cache_env):
        client, headers, _, _ = cache_env

        client.get("/suppliers", headers=headers)
        hits_after_warm = cache_module.cache.stats["hits"]

        client.delete("/suppliers/1", headers=headers)

        after = client.get("/suppliers", headers=headers)
        assert after.status_code == 200
        assert cache_module.cache.stats["hits"] == hits_after_warm

    def test_list_still_requires_auth(self, cache_env):
        """Auth must still execute on cache hit."""
        client, headers, _, _ = cache_env

        client.get("/suppliers", headers=headers)
        noauth = client.get("/suppliers")
        assert noauth.status_code == 401


# ══════════════════════════════════════════════
# Supplier detail cache tests
# ══════════════════════════════════════════════


class TestSupplierDetailCache:
    """Verify GET /suppliers/{id} caching."""

    def test_cold_miss_then_hit(self, cache_env):
        client, headers, _, _ = cache_env

        cold = client.get("/suppliers/1", headers=headers)
        assert cold.status_code == 200
        assert cold.json()["name"] == "UPS Ground"

        hits_after_cold = cache_module.cache.stats["hits"]

        warm = client.get("/suppliers/1", headers=headers)
        assert warm.status_code == 200
        assert warm.json() == cold.json()
        assert cache_module.cache.stats["hits"] == hits_after_cold + 1

    def test_different_ids_isolated(self, cache_env):
        client, headers, _, _ = cache_env

        s1 = client.get("/suppliers/1", headers=headers)
        s2 = client.get("/suppliers/2", headers=headers)

        assert s1.json()["id"] == 1
        assert s2.json()["id"] == 2
        assert s1.json()["name"] != s2.json()["name"]

    def test_rate_update_invalidates_detail(self, cache_env):
        client, headers, _, _ = cache_env

        client.get("/suppliers/1", headers=headers)
        hits_after_warm = cache_module.cache.stats["hits"]

        client.patch(
            "/suppliers/1/rate",
            json={"rate_per_shipment": 88.0},
            headers=headers,
        )

        after = client.get("/suppliers/1", headers=headers)
        assert after.status_code == 200
        assert after.json()["rate_per_shipment"] == 88.0
        assert cache_module.cache.stats["hits"] == hits_after_warm

    def test_delete_supplier_invalidates_detail(self, cache_env):
        client, headers, _, _ = cache_env

        client.get("/suppliers/1", headers=headers)
        client.delete("/suppliers/1", headers=headers)

        after = client.get("/suppliers/1", headers=headers)
        assert after.status_code == 404

    def test_detail_still_requires_auth(self, cache_env):
        """Auth must still execute on cache hit."""
        client, headers, _, _ = cache_env

        client.get("/suppliers/1", headers=headers)
        noauth = client.get("/suppliers/1")
        assert noauth.status_code == 401


# ══════════════════════════════════════════════
# Failed-mutation — cache must NOT be invalidated
# when the mutation raises an exception.
# Architecture enforces this: invalidate_prefix is
# called AFTER the mutation; if the mutation raises
# an HTTPException (400/404/422), the invalidation
# code never executes.
# ══════════════════════════════════════════════


class TestFailedMutationDoesNotInvalidate:
    """Negative tests: failed mutations must NOT invalidate cache.

    At least one test per domain (incidents + suppliers).
    """

    # -- Incidents domain ------------------------------------------------

    def test_invalid_status_transition_does_not_invalidate_summary(
        self, cache_env
    ):
        """PATCH with invalid transition (resolved->open) raises 400,
        cache.invalidate_prefix is never reached -> summary stays warm."""
        client, headers, inc_table, _ = cache_env

        # Create an incident
        create_resp = client.post(
            "/incidents",
            json={
                "title": "Test",
                "description": "Status transition test",
                "category": "lost_parcel",
                "origin": "customer",
                "branch": "la_office",
            },
            headers=headers,
        )
        inc_id = create_resp.json()["id"]

        # Move to resolved first
        client.patch(
            f"/incidents/{inc_id}/status",
            json={"status": "resolved"},
            headers=headers,
        )

        # Warm the summary cache
        client.get("/incidents/summary", headers=headers)
        hits_after_warm = cache_module.cache.stats["hits"]

        # Attempt invalid transition: resolved -> open (invalid)
        resp = client.patch(
            f"/incidents/{inc_id}/status",
            json={"status": "open"},
            headers=headers,
        )
        assert resp.status_code == 400

        # Summary must still be warm - cache was NOT invalidated
        after = client.get("/incidents/summary", headers=headers)
        assert after.status_code == 200
        assert cache_module.cache.stats["hits"] == hits_after_warm + 1

    def test_create_incident_missing_fields_does_not_invalidate_summary(
        self, cache_env
    ):
        """POST with missing title returns 400 before
        cache.invalidate_prefix is reached -> summary stays warm."""
        client, headers, _, _ = cache_env

        # Warm the summary cache
        client.get("/incidents/summary", headers=headers)
        hits_after_warm = cache_module.cache.stats["hits"]

        # Attempt creation with missing title
        resp = client.post(
            "/incidents",
            json={
                "description": "Missing title",
                "category": "lost_parcel",
                "origin": "customer",
                "branch": "la_office",
            },
            headers=headers,
        )
        assert resp.status_code == 400

        # Summary must still be warm
        after = client.get("/incidents/summary", headers=headers)
        assert after.status_code == 200
        assert cache_module.cache.stats["hits"] == hits_after_warm + 1

    # -- Suppliers domain ------------------------------------------------

    def test_create_supplier_invalid_currency_does_not_invalidate_list(
        self, cache_env
    ):
        """POST with invalid currency raises 422 before
        cache.invalidate_prefix is reached -> list stays warm."""
        client, headers, _, _ = cache_env

        # Warm the supplier list cache
        client.get("/suppliers", headers=headers)
        hits_after_warm = cache_module.cache.stats["hits"]

        # Attempt creation with invalid currency
        resp = client.post(
            "/suppliers",
            json={
                "name": "Bad Supplier",
                "country": "USA",
                "categories": ["carrier_last_mile"],
                "rate_per_shipment": 10.0,
                "currency": "INVALID",
                "status": "active",
            },
            headers=headers,
        )
        assert resp.status_code == 422

        # Supplier list must still be warm
        after = client.get("/suppliers", headers=headers)
        assert after.status_code == 200
        assert cache_module.cache.stats["hits"] == hits_after_warm + 1

    def test_delete_nonexistent_supplier_does_not_invalidate_list(
        self, cache_env
    ):
        """DELETE of a non-existent supplier returns 404 before
        cache.invalidate_prefix is reached -> list stays warm."""
        client, headers, _, _ = cache_env

        # Warm the supplier list cache
        client.get("/suppliers", headers=headers)
        hits_after_warm = cache_module.cache.stats["hits"]

        # Attempt delete of non-existent supplier
        resp = client.delete("/suppliers/9999", headers=headers)
        assert resp.status_code == 404

        # Supplier list must still be warm
        after = client.get("/suppliers", headers=headers)
        assert after.status_code == 200
        assert cache_module.cache.stats["hits"] == hits_after_warm + 1