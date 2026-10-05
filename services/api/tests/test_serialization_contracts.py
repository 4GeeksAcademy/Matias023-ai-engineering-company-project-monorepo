"""Serialization contract tests — Phase 3 implementation.

Verifies that every route with an explicit ``response_model``:
1. Returns HTTP 200 (or the documented status code).
2. Returns a body that validates against its declared schema.
3. Does NOT leak fields that are absent from the response model.

Uses the same isolated TinyDB + monkeypatch pattern as the existing test
suites, and prevents the unreachable production DATABASE_URL from blocking
TestClient(app) by setting ``DATABASE_URL=""`` before the app is imported.
"""

import os

# ── Prevent the production DATABASE_URL from blocking TestClient(app).
#    Must happen BEFORE ``from main import app`` because main.py calls
#    load_dotenv() at module level and init_db() at lifespan start.
#    The .env file contains APP_ENV=production and a stale Supabase URL.
#    python-dotenv does NOT override existing env vars by default, so we
#    pre-set safe values here.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ.pop("APP_ENV", None)

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from tinydb import TinyDB

from main import app
import routers.auth as auth_router_module
import routers.incidents as incidents_router_module
import routers.users as users_router_module
import security as security_module
from models import (
    DetailResponse,
    HealthResponse,
    IncidentSummaryResponse,
    RootResponse,
    UserListItemResponse,
)


# ── Helpers ─────────────────────────────────────────────────────────────


def _create_user_and_login(client) -> str:
    """Create a test user, log in, return a bearer token."""
    client.post(
        "/users",
        json={
            "email": "serialization-tester@example.com",
            "password": "strongpass123",
        },
    )
    resp = client.post(
        "/auth/login",
        json={
            "email": "serialization-tester@example.com",
            "password": "strongpass123",
        },
    )
    return resp.json()["access_token"]


def _authorization_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def bare_client():
    """TestClient with DATABASE_URL neutralised.

    No TinyDB isolation — suitable ONLY for endpoints that do not touch
    any database (``/``, ``/health``).
    """
    with TestClient(app) as client:
        yield client


@pytest.fixture
def isolated_client(tmp_path, monkeypatch):
    """TestClient with fully isolated TinyDB + auth environment.

    Every table reference across every module is monkeypatched so no test
    touches real/production data.  DATABASE_URL was already neutralised at
    module level so init_db() creates SQLite in-memory tables instead of
    trying to reach the unreachable Supabase pooler.
    """
    test_db = TinyDB(tmp_path / "serialization-test.json")
    test_users_table = test_db.table("users")
    test_profiles_table = test_db.table("profiles")
    test_incidents_table = test_db.table("incidents")
    test_reset_tokens_table = test_db.table("reset_tokens")

    monkeypatch.setattr(users_router_module, "users_table", test_users_table)
    monkeypatch.setattr(users_router_module, "profiles_table", test_profiles_table)
    monkeypatch.setattr(auth_router_module, "users_table", test_users_table)
    monkeypatch.setattr(security_module, "users_table", test_users_table)
    monkeypatch.setattr(security_module, "reset_tokens_table", test_reset_tokens_table)
    monkeypatch.setattr(incidents_router_module, "incidents_table", test_incidents_table)

    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-serialization-tests")

    with TestClient(app) as client:
        yield client


@pytest.fixture
def authed_client(isolated_client):
    """Return a (client, token) tuple with an authenticated session."""
    token = _create_user_and_login(isolated_client)
    return isolated_client, token


# ═══════════════════════════════════════════════════════════════════════════
# RootResponse
# ═══════════════════════════════════════════════════════════════════════════


class TestRootEndpoint:
    """GET / — RootResponse contract."""

    def test_root_returns_200(self, bare_client):
        resp = bare_client.get("/")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    def test_root_body_matches_root_response(self, bare_client):
        resp = bare_client.get("/")
        data = resp.json()

        # Validate against the schema
        validated = RootResponse(**data)
        assert validated.message == data["message"]
        assert validated.status == data["status"]

    def test_root_has_no_extra_fields(self, bare_client):
        resp = bare_client.get("/")
        data = resp.json()

        root_fields = RootResponse.model_fields
        for key in data:
            assert key in root_fields, (
                f"Unexpected field '{key}' in root response. "
                f"Expected only: {set(root_fields.keys())}"
            )

    def test_root_exact_field_values(self, bare_client):
        resp = bare_client.get("/")
        data = resp.json()

        assert data["message"] == "TrackFlow Supplier Directory API"
        assert data["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════════
# HealthResponse
# ═══════════════════════════════════════════════════════════════════════════


class TestHealthEndpoint:
    """GET /health — HealthResponse contract."""

    def test_health_returns_200(self, bare_client):
        resp = bare_client.get("/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    def test_health_body_matches_health_response(self, bare_client):
        resp = bare_client.get("/health")
        data = resp.json()

        validated = HealthResponse(**data)
        assert validated.status == data["status"]

    def test_health_has_no_extra_fields(self, bare_client):
        resp = bare_client.get("/health")
        data = resp.json()

        health_fields = HealthResponse.model_fields
        for key in data:
            assert key in health_fields, (
                f"Unexpected field '{key}' in health response. "
                f"Expected only: {set(health_fields.keys())}"
            )

    def test_health_exact_field_value(self, bare_client):
        resp = bare_client.get("/health")
        data = resp.json()
        assert data["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════════
# DetailResponse (DELETE /users/{user_id})
# ═══════════════════════════════════════════════════════════════════════════


class TestDeleteUserSerialization:
    """DELETE /users/{user_id} — DetailResponse contract."""

    def test_delete_own_user_returns_200(self, authed_client):
        client, token = authed_client
        # The authenticated user has id=1 (first created user)
        resp = client.delete("/users/1", headers=_authorization_header(token))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    def test_delete_response_matches_detail_response(self, authed_client):
        client, token = authed_client
        resp = client.delete("/users/1", headers=_authorization_header(token))
        data = resp.json()
        validated = DetailResponse(**data)
        assert validated.detail == data["detail"]

    def test_delete_response_has_no_user_object(self, authed_client):
        client, token = authed_client
        resp = client.delete("/users/1", headers=_authorization_header(token))
        data = resp.json()

        # Verify no sensitive or unexpected keys leak
        sensitive_keys = {"password", "hashed_password", "uuid", "id", "email", "role"}
        leaked = sensitive_keys & set(data.keys())
        assert not leaked, (
            f"DELETE response leaked sensitive fields: {leaked}. "
            f"Expected only: 'detail'"
        )

    def test_delete_response_has_only_detail(self, authed_client):
        client, token = authed_client
        resp = client.delete("/users/1", headers=_authorization_header(token))
        data = resp.json()
        detail_fields = DetailResponse.model_fields
        for key in data:
            assert key in detail_fields, (
                f"Unexpected field '{key}' in DELETE response. "
                f"Expected only: {set(detail_fields.keys())}"
            )

    def test_delete_response_detail_text(self, authed_client):
        client, token = authed_client
        resp = client.delete("/users/1", headers=_authorization_header(token))
        data = resp.json()
        assert data["detail"] == "User deleted successfully"


# ═══════════════════════════════════════════════════════════════════════════
# IncidentSummaryResponse (GET /incidents/summary)
# ═══════════════════════════════════════════════════════════════════════════


class TestIncidentSummarySerialization:
    """GET /incidents/summary — IncidentSummaryResponse contract."""

    def test_summary_returns_200(self, authed_client):
        client, token = authed_client
        resp = client.get("/incidents/summary", headers=_authorization_header(token))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    def test_summary_empty_db(self, authed_client):
        client, token = authed_client
        resp = client.get("/incidents/summary", headers=_authorization_header(token))
        data = resp.json()
        validated = IncidentSummaryResponse(**data)
        assert validated.total == 0
        assert all(v == 0 for v in validated.by_status.values())
        assert all(v == 0 for v in validated.by_category.values())
        assert all(v == 0 for v in validated.by_origin.values())
        assert all(v == 0 for v in validated.by_branch.values())

    def test_summary_with_data(self, isolated_client):
        """Seed incidents via the API and verify summary aggregation."""
        token = _create_user_and_login(isolated_client)
        headers = _authorization_header(token)

        # Create incidents via POST
        # Create incidents with different statuses via POST + PATCH
        payloads = [
            {"title": "Lost parcel", "description": "desc", "category": "lost_parcel", "origin": "customer", "branch": "la_office"},
            {"title": "Delivery fail", "description": "desc", "category": "delivery_failure", "origin": "customer", "branch": "la_warehouse"},
            {"title": "Inventory issue", "description": "desc", "category": "inventory_discrepancy", "origin": "internal", "branch": "central"},
            {"title": "Carrier problem", "description": "desc", "category": "carrier_issue", "origin": "branch", "branch": "zaragoza_warehouse"},
            {"title": "Warehouse damage", "description": "desc", "category": "warehouse_incident", "origin": "internal", "branch": "la_warehouse"},
        ]
        incident_ids = []
        for p in payloads:
            resp = isolated_client.post("/api/incidents", json=p, headers=headers)
            incident_ids.append(resp.json()["id"])

        # Change statuses through VALID transitions to get distinct aggregations
        isolated_client.patch(f"/api/incidents/{incident_ids[1]}/status", json={"status": "in_progress"}, headers=headers)
        isolated_client.patch(f"/api/incidents/{incident_ids[2]}/status", json={"status": "in_progress"}, headers=headers)
        isolated_client.patch(f"/api/incidents/{incident_ids[2]}/status", json={"status": "resolved"}, headers=headers)
        isolated_client.patch(f"/api/incidents/{incident_ids[4]}/status", json={"status": "discarded"}, headers=headers)

        resp = isolated_client.get("/incidents/summary", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        validated = IncidentSummaryResponse(**data)

        assert validated.total == 5
        assert validated.by_status["open"] == 2, f"Expected 2 open, got {validated.by_status['open']}"
        assert validated.by_status["in_progress"] == 1, f"Expected 1 in_progress, got {validated.by_status['in_progress']}"
        assert validated.by_status["resolved"] == 1, f"Expected 1 resolved, got {validated.by_status['resolved']}"
        assert validated.by_status["discarded"] == 1, f"Expected 1 discarded, got {validated.by_status['discarded']}"

    def test_summary_has_no_extra_fields(self, authed_client):
        client, token = authed_client
        resp = client.get("/incidents/summary", headers=_authorization_header(token))
        data = resp.json()
        summary_fields = IncidentSummaryResponse.model_fields
        for key in data:
            assert key in summary_fields, (
                f"Unexpected field '{key}' in summary response. "
                f"Expected only: {set(summary_fields.keys())}"
            )

    def test_summary_all_values_are_int(self, authed_client):
        client, token = authed_client
        resp = client.get("/incidents/summary", headers=_authorization_header(token))
        data = resp.json()
        assert isinstance(data["total"], int)
        for agg_key in ("by_status", "by_category", "by_origin", "by_branch"):
            agg = data[agg_key]
            for k, v in agg.items():
                assert isinstance(v, int), (
                    f"{agg_key}[{k!r}] is {type(v).__name__}, expected int"
                )


# ═══════════════════════════════════════════════════════════════════════════
# UserListItemResponse (GET /users)
# ═══════════════════════════════════════════════════════════════════════════


class TestListUsersSerialization:
    """GET /users — UserListItemResponse contract."""

    def test_list_users_returns_200(self, authed_client):
        client, token = authed_client
        resp = client.get("/users", headers=_authorization_header(token))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    def test_list_users_items_match_user_list_item_response(self, authed_client):
        client, token = authed_client
        resp = client.get("/users", headers=_authorization_header(token))
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"

        # Each item must validate against UserListItemResponse
        adapter = TypeAdapter(list[UserListItemResponse])
        validated = adapter.validate_python(data)
        assert len(validated) == len(data)

    def test_list_users_no_uuid_in_items(self, authed_client):
        client, token = authed_client
        resp = client.get("/users", headers=_authorization_header(token))
        data = resp.json()
        for i, item in enumerate(data):
            assert "uuid" not in item, (
                f"Item {i} leaks 'uuid' field: {item.get('uuid')!r}"
            )

    def test_list_users_no_password_fields_in_items(self, authed_client):
        client, token = authed_client
        resp = client.get("/users", headers=_authorization_header(token))
        data = resp.json()
        sensitive = {"password", "hashed_password"}
        for i, item in enumerate(data):
            leaked = sensitive & set(item.keys())
            assert not leaked, (
                f"Item {i} leaks sensitive fields: {leaked}"
            )

    def test_list_users_items_have_only_expected_fields(self, authed_client):
        client, token = authed_client
        resp = client.get("/users", headers=_authorization_header(token))
        data = resp.json()
        allowed_fields = set(UserListItemResponse.model_fields.keys())
        for i, item in enumerate(data):
            extra = set(item.keys()) - allowed_fields
            assert not extra, (
                f"Item {i} has unexpected fields: {extra}. "
                f"Allowed: {allowed_fields}"
            )

    def test_list_users_item_field_types(self, authed_client):
        client, token = authed_client
        resp = client.get("/users", headers=_authorization_header(token))
        data = resp.json()
        for i, item in enumerate(data):
            assert isinstance(item["id"], int), f"Item {i}: id is not int"
            assert isinstance(item["email"], str), f"Item {i}: email is not str"
            assert isinstance(item["is_active"], bool), f"Item {i}: is_active is not bool"
            assert isinstance(item["role"], str), f"Item {i}: role is not str"
            # created_at should be a string (ISO datetime)
            assert isinstance(item["created_at"], str), f"Item {i}: created_at is not str"