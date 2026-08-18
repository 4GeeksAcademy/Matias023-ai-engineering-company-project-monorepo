from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tinydb import TinyDB

from services.api import database
from services.api.main import app
from services.api.seed import seed_suppliers


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_file = tmp_path / "suppliers_test.json"
    monkeypatch.setenv("SUPPLIERS_DB_PATH", str(db_file))
    database.close_db()

    with TestClient(app) as test_client:
        yield test_client

    database.close_db()


@pytest.fixture
def seeded_client(client: TestClient) -> TestClient:
    seed_suppliers()
    return client


def _valid_supplier_payload() -> dict:
    return {
        "name": "Atlas Carrier",
        "country": "USA",
        "categories": ["carrier_last_mile"],
        "rate_per_shipment": 9.5,
        "currency": "USD",
        "status": "active",
        "service_zone": "West Coast",
        "contact_email": "ops@atlas.test",
        "notes": "Proveedor de prueba",
    }


def test_post_supplier_valid(client: TestClient) -> None:
    response = client.post("/suppliers", json=_valid_supplier_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["name"] == "Atlas Carrier"
    assert body["updated_at"]


def test_post_supplier_rate_zero_422(client: TestClient) -> None:
    payload = _valid_supplier_payload()
    payload["rate_per_shipment"] = 0
    response = client.post("/suppliers", json=payload)
    assert response.status_code == 422


def test_post_supplier_rate_negative_422(client: TestClient) -> None:
    payload = _valid_supplier_payload()
    payload["rate_per_shipment"] = -1
    response = client.post("/suppliers", json=payload)
    assert response.status_code == 422


def test_post_supplier_invalid_status_422(client: TestClient) -> None:
    payload = _valid_supplier_payload()
    payload["status"] = "paused"
    response = client.post("/suppliers", json=payload)
    assert response.status_code == 422


def test_post_supplier_invalid_category_422(client: TestClient) -> None:
    payload = _valid_supplier_payload()
    payload["categories"] = ["unknown_category"]
    response = client.post("/suppliers", json=payload)
    assert response.status_code == 422


def test_post_supplier_empty_categories_422(client: TestClient) -> None:
    payload = _valid_supplier_payload()
    payload["categories"] = []
    response = client.post("/suppliers", json=payload)
    assert response.status_code == 422


def test_post_supplier_usa_eur_422(client: TestClient) -> None:
    payload = _valid_supplier_payload()
    payload["currency"] = "EUR"
    response = client.post("/suppliers", json=payload)
    assert response.status_code == 422


def test_post_supplier_spain_usd_422(client: TestClient) -> None:
    payload = _valid_supplier_payload()
    payload["country"] = "Spain"
    payload["currency"] = "USD"
    response = client.post("/suppliers", json=payload)
    assert response.status_code == 422


def test_get_all_suppliers(seeded_client: TestClient) -> None:
    response = seeded_client.get("/suppliers")
    assert response.status_code == 200
    assert len(response.json()) == 15


def test_filter_country_usa(seeded_client: TestClient) -> None:
    response = seeded_client.get("/suppliers", params={"country": "USA"})
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 9
    assert all(item["country"] == "USA" for item in items)


def test_filter_country_spain(seeded_client: TestClient) -> None:
    response = seeded_client.get("/suppliers", params={"country": "Spain"})
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 6
    assert all(item["country"] == "Spain" for item in items)


def test_filter_category(seeded_client: TestClient) -> None:
    response = seeded_client.get("/suppliers", params={"category": "carrier_last_mile"})
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 9
    assert all("carrier_last_mile" in item["categories"] for item in items)


def test_filter_multicategory_supplier_included(seeded_client: TestClient) -> None:
    response = seeded_client.get(
        "/suppliers", params={"category": "carrier_international", "country": "USA"}
    )
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["name"] == "DHL Express USA"


def test_get_by_id_exists(seeded_client: TestClient) -> None:
    response = seeded_client.get("/suppliers/1")
    assert response.status_code == 200
    assert response.json()["id"] == 1


def test_get_by_id_not_found(client: TestClient) -> None:
    response = client.get("/suppliers/999")
    assert response.status_code == 404


def test_patch_rate_valid(client: TestClient) -> None:
    created = client.post("/suppliers", json=_valid_supplier_payload()).json()
    supplier_id = created["id"]

    response = client.patch(
        f"/suppliers/{supplier_id}/rate", json={"rate_per_shipment": 11.25}
    )
    assert response.status_code == 200
    assert response.json()["rate_per_shipment"] == 11.25


def test_patch_rate_updates_updated_at(client: TestClient) -> None:
    created = client.post("/suppliers", json=_valid_supplier_payload()).json()
    supplier_id = created["id"]
    original_updated_at = created["updated_at"]

    response = client.patch(
        f"/suppliers/{supplier_id}/rate", json={"rate_per_shipment": 11.25}
    )
    assert response.status_code == 200
    assert response.json()["updated_at"] != original_updated_at


def test_patch_rate_zero_422(client: TestClient) -> None:
    created = client.post("/suppliers", json=_valid_supplier_payload()).json()
    supplier_id = created["id"]

    response = client.patch(f"/suppliers/{supplier_id}/rate", json={"rate_per_shipment": 0})
    assert response.status_code == 422


def test_patch_status_valid(client: TestClient) -> None:
    created = client.post("/suppliers", json=_valid_supplier_payload()).json()
    supplier_id = created["id"]

    response = client.patch(f"/suppliers/{supplier_id}/status", json={"status": "suspended"})
    assert response.status_code == 200
    assert response.json()["status"] == "suspended"


def test_patch_status_invalid_422(client: TestClient) -> None:
    created = client.post("/suppliers", json=_valid_supplier_payload()).json()
    supplier_id = created["id"]

    response = client.patch(f"/suppliers/{supplier_id}/status", json={"status": "archived"})
    assert response.status_code == 422


def test_delete_existing(client: TestClient) -> None:
    created = client.post("/suppliers", json=_valid_supplier_payload()).json()
    supplier_id = created["id"]

    response = client.delete(f"/suppliers/{supplier_id}")
    assert response.status_code == 204


def test_delete_nonexistent_404(client: TestClient) -> None:
    response = client.delete("/suppliers/999")
    assert response.status_code == 404


def test_seeder_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "seed_idempotent.json"
    monkeypatch.setenv("SUPPLIERS_DB_PATH", str(db_file))
    database.close_db()

    inserted_1, total_1 = seed_suppliers()
    inserted_2, total_2 = seed_suppliers()

    assert inserted_1 == 15
    assert total_1 == 15
    assert inserted_2 == 0
    assert total_2 == 15


def test_tinydb_persistence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "persistent.json"
    monkeypatch.setenv("SUPPLIERS_DB_PATH", str(db_file))
    database.close_db()

    with TestClient(app) as test_client:
        response = test_client.post("/suppliers", json=_valid_supplier_payload())
        assert response.status_code == 201

    database.close_db()

    db = TinyDB(db_file)
    suppliers = db.table("suppliers").all()
    db.close()
    assert len(suppliers) == 1
