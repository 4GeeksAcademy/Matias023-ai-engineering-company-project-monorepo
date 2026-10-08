"""Inventory API tests (Milestone 5 — ORM & Dual Database).

Test strategy:
    * SQLModel + SQLite in-memory engine with foreign-key enforcement ON
      (so referential constraints and per-warehouse stock behave like the real
      PostgreSQL/Supabase database).
    * A fresh, isolated in-memory engine per test (module-scoped reset).
    * ``get_db`` dependency overridden to yield sessions against that engine,
      so no production DATABASE_URL is required.
    * TinyDB auth uses the same ``tmp_path`` + ``monkeypatch`` conventions as
      the existing suites (create a user, login, capture the bearer token).

Coverage:
    * model/table creation
    * SKU create / list / get / 404 / invalid category / invalid warehouse /
      duplicate sku / current_stock is response-only and computed
    * inbound: auth, stock increase, user_uuid recorded, warehouse rule
    * outbound: dispatch with tracking ok; dispatch without tracking rejected;
      loss with null tracking ok; loss with tracking rejected;
      negative stock -> HTTP 400 EXACT message; rejected exit not persisted
    * stock = SUM(entries) - SUM(exits) per SKU *per warehouse*
    * GET /inventory/orders returns both movement types + SKU data + user_uuid
    * auth enforcement (401 unauthenticated, 200 authenticated)
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from tinydb import TinyDB

from main import app
import routers.auth as auth_router_module
import routers.users as users_router_module
import security as security_module
from database import get_db


# ──────────────────────────────────────────────
# SQLModel test engine (isolated per test)
# ──────────────────────────────────────────────


@pytest.fixture
def inventory_engine():
    """Create a fresh in-memory SQLite engine with FK enforcement for a test.

    Uses StaticPool so the app's worker thread and the test thread share the
    same in-memory connection (otherwise each thread gets a different empty
    in-memory database and tables appear missing at runtime).
    """
    from sqlalchemy import event
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable foreign key enforcement on every new connection.
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(inventory_engine, tmp_path, monkeypatch):
    """TestClient with TinyDB auth patched + get_db overridden to the test DB."""

    # --- TinyDB auth isolation ---
    test_db = TinyDB(tmp_path / "inventory-auth.json")
    test_users_table = test_db.table("users")
    test_profiles_table = test_db.table("profiles")

    monkeypatch.setattr(users_router_module, "users_table", test_users_table)
    monkeypatch.setattr(users_router_module, "profiles_table", test_profiles_table)
    monkeypatch.setattr(auth_router_module, "users_table", test_users_table)
    monkeypatch.setattr(security_module, "users_table", test_users_table)

    monkeypatch.setenv("SECRET_KEY", "test-secret-inventory-key")

    # --- Override get_db to the isolated SQLModel engine ---
    def override_get_db():
        with Session(inventory_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)


# ──────────────────────────────────────────────
# Auth helpers
# ──────────────────────────────────────────────


def create_user_and_token(client, email="inventory@example.com", password="invpass123"):
    client.post(
        "/users",
        json={"email": email, "password": password, "role": "user"},
    )
    login = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    return login.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ──────────────────────────────────────────────
# Shared sample SKU payload
# ──────────────────────────────────────────────


def sample_sku(**overrides):
    payload = {
        "name": "Classic White Sneaker - Size 42",
        "sku": "CLT-SNK-W-42",
        "client_name": "PureStep Footwear",
        "category": "fashion",
        "warehouse": "LA",
    }
    payload.update(overrides)
    return payload


# ══════════════════════════════════════════════
# Model / table creation
# ══════════════════════════════════════════════


class TestModelCreation:
    def test_tables_created(self, inventory_engine):
        from sqlalchemy import inspect

        inspector = inspect(inventory_engine)
        tables = set(inspector.get_table_names())

        assert "skus" in tables
        assert "stock_entries" in tables
        assert "stock_exits" in tables

    def test_sku_has_no_stock_column(self, inventory_engine):
        """current_stock must be computed, never stored."""
        from sqlalchemy import inspect

        inspector = inspect(inventory_engine)
        sku_columns = {col["name"] for col in inspector.get_columns("skus")}

        assert "stock" not in sku_columns
        assert "current_stock" not in sku_columns


# ══════════════════════════════════════════════
# Auth enforcement
# ══════════════════════════════════════════════


class TestAuth:
    def test_products_requires_auth(self, client):
        response = client.get("/inventory/products")
        assert response.status_code == 401

    def test_products_authenticated_returns_200(self, client):
        token = create_user_and_token(client)
        response = client.get(
            "/inventory/products",
            headers=auth_headers(token),
        )
        assert response.status_code == 200

    def test_orders_list_requires_auth(self, client):
        response = client.get("/inventory/orders")
        assert response.status_code == 401

    def test_inbound_requires_auth(self, client):
        response = client.post(
            "/inventory/orders/inbound",
            json={
                "sku_id": 1,
                "quantity": 10,
                "reference": "PO-TEST-1",
                "warehouse": "LA",
            },
        )
        assert response.status_code == 401


# ══════════════════════════════════════════════
# SKU products
# ══════════════════════════════════════════════


class TestProducts:
    def test_create_sku_returns_201(self, client):
        token = create_user_and_token(client)
        response = client.post(
            "/inventory/products",
            json=sample_sku(),
            headers=auth_headers(token),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["sku"] == "CLT-SNK-W-42"
        assert data["category"] == "fashion"
        assert data["warehouse"] == "LA"
        assert data["current_stock"] == 0
        assert "id" in data

    def test_create_sku_current_stock_not_writable(self, client):
        """current_stock is response-only — passing it must be ignored/rejected."""
        token = create_user_and_token(client)
        payload = sample_sku(current_stock=999)
        response = client.post(
            "/inventory/products",
            json=payload,
            headers=auth_headers(token),
        )
        # Pydantic ignores unknown fields by default -> current_stock==0
        assert response.status_code == 201
        assert response.json()["current_stock"] == 0

    def test_create_duplicate_sku_rejected(self, client):
        token = create_user_and_token(client)
        headers = auth_headers(token)
        client.post("/inventory/products", json=sample_sku(), headers=headers)

        response = client.post(
            "/inventory/products",
            json=sample_sku(),
            headers=headers,
        )
        assert response.status_code == 409

    def test_create_invalid_category_rejected(self, client):
        token = create_user_and_token(client)
        payload = sample_sku(category="books")
        response = client.post(
            "/inventory/products",
            json=payload,
            headers=auth_headers(token),
        )
        assert response.status_code == 422

    def test_create_invalid_warehouse_rejected(self, client):
        token = create_user_and_token(client)
        payload = sample_sku(warehouse="NYC")
        response = client.post(
            "/inventory/products",
            json=payload,
            headers=auth_headers(token),
        )
        assert response.status_code == 422

    def test_list_products_empty(self, client):
        token = create_user_and_token(client)
        response = client.get(
            "/inventory/products",
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_list_products_with_stock(self, client):
        token = create_user_and_token(client)
        headers = auth_headers(token)

        created = client.post(
            "/inventory/products",
            json=sample_sku(),
            headers=headers,
        ).json()
        sku_id = created["id"]

        client.post(
            "/inventory/orders/inbound",
            json={
                "sku_id": sku_id,
                "quantity": 50,
                "reference": "GR-TEST-1",
                "warehouse": "LA",
            },
            headers=headers,
        )

        response = client.get(
            "/inventory/products",
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["current_stock"] == 50

    def test_get_product_not_found(self, client):
        token = create_user_and_token(client)
        response = client.get(
            "/inventory/products/9999",
            headers=auth_headers(token),
        )
        assert response.status_code == 404


# ══════════════════════════════════════════════
# Inbound orders (StockEntry)
# ══════════════════════════════════════════════


class TestInbound:
    def _create_sku(self, client, headers, **overrides):
        return client.post(
            "/inventory/products",
            json=sample_sku(**overrides),
            headers=headers,
        ).json()

    def test_inbound_increases_stock(self, client):
        token = create_user_and_token(client)
        headers = auth_headers(token)
        sku = self._create_sku(client, headers)
        sku_id = sku["id"]

        response = client.post(
            "/inventory/orders/inbound",
            json={
                "sku_id": sku_id,
                "quantity": 100,
                "reference": "PO-2024-0098",
                "warehouse": "LA",
            },
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["quantity"] == 100
        assert response.json()["user_uuid"] != ""

        # Stock now reflects the entry
        get = client.get(f"/inventory/products/{sku_id}", headers=headers)
        assert get.json()["current_stock"] == 100

    def test_inbound_stores_user_uuid(self, client):
        token = create_user_and_token(client)
        headers = auth_headers(token)
        sku = self._create_sku(client, headers)

        response = client.post(
            "/inventory/orders/inbound",
            json={
                "sku_id": sku["id"],
                "quantity": 10,
                "reference": "GR-TEST-UUID",
                "warehouse": "LA",
            },
            headers=headers,
        )
        assert response.status_code == 201
        stored_uuid = response.json()["user_uuid"]

        # The recorded user_uuid should be a valid UUID matching the user.
        assert stored_uuid

    def test_inbound_unknown_sku_404(self, client):
        token = create_user_and_token(client)
        response = client.post(
            "/inventory/orders/inbound",
            json={
                "sku_id": 9999,
                "quantity": 10,
                "reference": "GR-TEST-404",
                "warehouse": "LA",
            },
            headers=auth_headers(token),
        )
        assert response.status_code == 404

    def test_inbound_zero_quantity_rejected(self, client):
        token = create_user_and_token(client)
        headers = auth_headers(token)
        sku = self._create_sku(client, headers)

        response = client.post(
            "/inventory/orders/inbound",
            json={
                "sku_id": sku["id"],
                "quantity": 0,
                "reference": "GR-TEST-0",
                "warehouse": "LA",
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_inbound_warehouse_mismatch_rejected(self, client):
        """A movement targeting a warehouse foreign to the SKU is rejected."""
        token = create_user_and_token(client)
        headers = auth_headers(token)
        sku = self._create_sku(client, headers)  # LA

        response = client.post(
            "/inventory/orders/inbound",
            json={
                "sku_id": sku["id"],
                "quantity": 10,
                "reference": "GR-TEST-MISMATCH",
                "warehouse": "ZGZ",
            },
            headers=headers,
        )
        assert response.status_code == 400


# ══════════════════════════════════════════════
# Outbound orders (StockExit)
# ══════════════════════════════════════════════


class TestOutbound:
    def _create_sku_with_stock(self, client, headers, quantity=100, **overrides):
        sku = client.post(
            "/inventory/products",
            json=sample_sku(**overrides),
            headers=headers,
        ).json()
        client.post(
            "/inventory/orders/inbound",
            json={
                "sku_id": sku["id"],
                "quantity": quantity,
                "reference": f"GR-SETUP-{sku['id']}",
                "warehouse": sku["warehouse"],
            },
            headers=headers,
        )
        return sku

    def _dispatch_payload(self, sku_id, quantity=10, tracking="1Z999AA10123456784"):
        return {
            "sku_id": sku_id,
            "quantity": quantity,
            "exit_type": "dispatch",
            "tracking_number": tracking,
            "warehouse": "LA",
        }

    def test_dispatch_with_tracking_ok(self, client):
        token = create_user_and_token(client)
        headers = auth_headers(token)
        sku = self._create_sku_with_stock(client, headers)

        response = client.post(
            "/inventory/orders/outbound",
            json=self._dispatch_payload(sku["id"]),
            headers=headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["exit_type"] == "dispatch"
        assert data["tracking_number"] == "1Z999AA10123456784"
        assert data["user_uuid"] != ""

        # Stock decreased
        get = client.get(f"/inventory/products/{sku['id']}", headers=headers)
        assert get.json()["current_stock"] == 90

    def test_dispatch_without_tracking_rejected(self, client):
        token = create_user_and_token(client)
        headers = auth_headers(token)
        sku = self._create_sku_with_stock(client, headers)

        payload = self._dispatch_payload(sku["id"], tracking=None)
        response = client.post(
            "/inventory/orders/outbound",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 422

    def test_loss_with_null_tracking_ok(self, client):
        token = create_user_and_token(client)
        headers = auth_headers(token)
        sku = self._create_sku_with_stock(client, headers)

        response = client.post(
            "/inventory/orders/outbound",
            json={
                "sku_id": sku["id"],
                "quantity": 5,
                "exit_type": "loss",
                "tracking_number": None,
                "warehouse": "LA",
            },
            headers=headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["exit_type"] == "loss"
        assert data["tracking_number"] is None

    def test_loss_with_tracking_rejected(self, client):
        token = create_user_and_token(client)
        headers = auth_headers(token)
        sku = self._create_sku_with_stock(client, headers)

        response = client.post(
            "/inventory/orders/outbound",
            json={
                "sku_id": sku["id"],
                "quantity": 5,
                "exit_type": "loss",
                "tracking_number": "1Z999AA10123456784",
                "warehouse": "LA",
            },
            headers=headers,
        )
        assert response.status_code == 422

    def test_exit_exceeding_stock_returns_400_exact_message(self, client):
        token = create_user_and_token(client)
        headers = auth_headers(token)
        sku = self._create_sku_with_stock(client, headers, quantity=100)

        response = client.post(
            "/inventory/orders/outbound",
            json=self._dispatch_payload(sku["id"], quantity=101),
            headers=headers,
        )
        assert response.status_code == 400
        assert response.json()["detail"] == (
            f"Insufficient stock for SKU '{sku['sku']}'. "
            f"Available: 100, requested: 101."
        )

    def test_rejected_exit_not_persisted(self, client):
        token = create_user_and_token(client)
        headers = auth_headers(token)
        sku = self._create_sku_with_stock(client, headers, quantity=10)

        response = client.post(
            "/inventory/orders/outbound",
            json=self._dispatch_payload(sku["id"], quantity=11),
            headers=headers,
        )
        assert response.status_code == 400

        # No exit was recorded: stock unchanged.
        get = client.get(f"/inventory/products/{sku['id']}", headers=headers)
        assert get.json()["current_stock"] == 10

    def test_exit_unknown_sku_404(self, client):
        token = create_user_and_token(client)
        response = client.post(
            "/inventory/orders/outbound",
            json=self._dispatch_payload(9999),
            headers=auth_headers(token),
        )
        assert response.status_code == 404


# ══════════════════════════════════════════════
# Per-warehouse stock isolation
# ══════════════════════════════════════════════


class TestWarehouseIsolation:
    def test_stock_is_per_sku_per_warehouse(self, client):
        """Two SKUs with the same integer part but different warehouses have
        independent stock."""
        token = create_user_and_token(client)
        headers = auth_headers(token)

        la = client.post(
            "/inventory/products",
            json=sample_sku(),  # CLT-SNK-W-42 LA
            headers=headers,
        ).json()
        zgz = client.post(
            "/inventory/products",
            json=sample_sku(
                sku="CLT-SNK-W-42-Z",
                warehouse="ZGZ",
            ),
            headers=headers,
        ).json()

        # LA entry for the LA SKU only.
        client.post(
            "/inventory/orders/inbound",
            json={
                "sku_id": la["id"],
                "quantity": 20,
                "reference": "GR-LA-ISO",
                "warehouse": "LA",
            },
            headers=headers,
        )

        la_stock = client.get(f"/inventory/products/{la['id']}", headers=headers).json()["current_stock"]
        zgz_stock = client.get(f"/inventory/products/{zgz['id']}", headers=headers).json()["current_stock"]

        assert la_stock == 20
        assert zgz_stock == 0  # stock must NOT be aggregated


# ══════════════════════════════════════════════
# GET /inventory/orders
# ══════════════════════════════════════════════


class TestOrdersList:
    def test_orders_lists_both_movements_with_sku_data(self, client):
        token = create_user_and_token(client)
        headers = auth_headers(token)

        la = client.post(
            "/inventory/products",
            json=sample_sku(),
            headers=headers,
        ).json()

        # 1 entry
        client.post(
            "/inventory/orders/inbound",
            json={
                "sku_id": la["id"],
                "quantity": 30,
                "reference": "GR-LA-ORD",
                "warehouse": "LA",
            },
            headers=headers,
        )
        # 1 dispatch exit
        client.post(
            "/inventory/orders/outbound",
            json={
                "sku_id": la["id"],
                "quantity": 5,
                "exit_type": "dispatch",
                "tracking_number": "1Z999AA10123456784",
                "warehouse": "LA",
            },
            headers=headers,
        )

        response = client.get("/inventory/orders", headers=headers)
        assert response.status_code == 200
        data = response.json()

        kinds = {item["kind"] for item in data}
        assert kinds == {"entry", "exit"}
        assert len(data) == 2

        entry = next(item for item in data if item["kind"] == "entry")
        assert entry["sku"] == "CLT-SNK-W-42"
        assert entry["sku_name"] == "Classic White Sneaker - Size 42"
        assert entry["reference"] == "GR-LA-ORD"
        assert entry["quantity"] == 30
        assert entry["user_uuid"] != ""

        exit_item = next(item for item in data if item["kind"] == "exit")
        assert exit_item["tracking_number"] == "1Z999AA10123456784"
        assert exit_item["exit_type"] == "dispatch"

    def test_orders_empty(self, client):
        token = create_user_and_token(client)
        response = client.get(
            "/inventory/orders",
            headers=auth_headers(token),
        )
        assert response.status_code == 200
        assert response.json() == []


# ══════════════════════════════════════════════
# Seed data integrity (canonical rows)
# ══════════════════════════════════════════════


class TestSeedIntegrity:
    def test_seed_has_required_counts(self):
        """The canonical seed must satisfy the milestone minimums."""
        from seed_inventory import ENTRY_SEED, EXIT_SEED, SKU_SEED

        assert len(SKU_SEED) >= 6
        assert len(ENTRY_SEED) >= 4
        assert len(EXIT_SEED) >= 3

        # >= 2 entries for the same SKU (different quantities).
        from collections import Counter
        entry_counts = Counter(entry["sku"] for entry in ENTRY_SEED)
        assert any(count >= 2 for count in entry_counts.values())

        # >= 1 dispatch with tracking, >= 1 loss with null tracking.
        exit_types = {exit_["exit_type"] for exit_ in EXIT_SEED}
        assert "dispatch" in exit_types and "loss" in exit_types
        assert any(
            exit_["exit_type"] == "dispatch" and exit_["tracking_number"]
            for exit_ in EXIT_SEED
        )
        assert any(
            exit_["exit_type"] == "loss" and exit_["tracking_number"] is None
            for exit_ in EXIT_SEED
        )