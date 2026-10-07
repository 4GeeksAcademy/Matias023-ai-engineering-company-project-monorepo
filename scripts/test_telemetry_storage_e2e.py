"""End-to-end test for telemetry event storage.

Covers:
  1. Technical event (real)  — an event that a real frontend or backend sends
  2. Business event  (real)  — an event carrying business-domain properties
  3. Inventory entry event   — inbound_registered (actual business event)
  4. Inventory exit event    — outbound_registered (actual business event)
  5. ≥ 5 rows stored in the telemetry_events table
  6. Mixed batch with valid AND invalid events (valid stored, invalid rejected)

Usage:
    # Start the API first, then run:
    uv run python scripts/test_telemetry_storage_e2e.py

    Or against a running server:
    python scripts/test_telemetry_storage_e2e.py --url http://localhost:8000
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx


BASE_URL = "http://localhost:8000"


def _event(event_type: str, properties: dict, **overrides) -> dict:
    """Build a valid telemetry event dictionary."""
    payload = {
        "eventId": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "sessionId": str(uuid4()),
        "userId": str(uuid4()),
        "event_type": event_type,
        "schemaVersion": "1.0",
        "requestId": str(uuid4()),
        "properties": properties,
    }
    payload.update(overrides)
    return payload


def _post_batch(client: httpx.Client, events: list[dict]) -> dict:
    return client.post(
        f"{BASE_URL}/telemetry/events",
        json={"events": events},
    ).json()


def run_e2e():
    parser = argparse.ArgumentParser(description="E2E test for telemetry storage")
    parser.add_argument("--url", default=BASE_URL, help="API base URL")
    args = parser.parse_args()
    global BASE_URL
    BASE_URL = args.url.rstrip("/")

    print(f"🔍 Target API: {BASE_URL}/telemetry/events")
    print()

    with httpx.Client(timeout=10) as client:
        # ── 1. Technical event ──────────────────────────────────────
        print("1️⃣  Technical event: api_server_error …", end=" ", flush=True)
        tech_event = _event(
            "api_server_error",
            {
                "path": "/inventory/products/999",
                "http_method": "GET",
                "error_code": "INTERNAL_ERROR",
                "status_code": 500,
            },
        )
        res = _post_batch(client, [tech_event])
        assert res["stored"] == 1, f"Expected stored=1, got {res}"
        assert res["rejected"] == 0
        print(f"✅  stored={res['stored']}")

        # ── 2. Business event ───────────────────────────────────────
        print("2️⃣  Business event: incident_created …", end=" ", flush=True)
        biz_event = _event(
            "incident_created",
            {
                "incident_id": 42,
                "category": "lost_parcel",
                "origin": "branch",
                "branch": "la_warehouse",
                "status": "open",
                "title_length": 87,
            },
        )
        res = _post_batch(client, [biz_event])
        assert res["stored"] == 1
        assert res["rejected"] == 0
        print(f"✅  stored={res['stored']}")

        # ── 3. Inventory entry event ────────────────────────────────
        print("3️⃣  Inventory entry: inbound_registered …", end=" ", flush=True)
        entry_event = _event(
            "inbound_registered",
            {
                "entry_id": 101,
                "sku_id": 5,
                "sku_code": "CLT-SNK-W-42",
                "quantity": 500,
                "warehouse": "LA",
                "category": "fashion",
            },
        )
        res = _post_batch(client, [entry_event])
        assert res["stored"] == 1
        assert res["rejected"] == 0
        print(f"✅  stored={res['stored']}")

        # ── 4. Inventory exit event ─────────────────────────────────
        print("4️⃣  Inventory exit: outbound_registered …", end=" ", flush=True)
        exit_event = _event(
            "outbound_registered",
            {
                "exit_id": 201,
                "sku_id": 5,
                "sku_code": "CLT-SNK-W-42",
                "quantity": 10,
                "exit_type": "dispatch",
                "warehouse": "LA",
                "category": "fashion",
                "has_tracking": True,
            },
        )
        res = _post_batch(client, [exit_event])
        assert res["stored"] == 1
        assert res["rejected"] == 0
        print(f"✅  stored={res['stored']}")

        # ── 5. Additional events to reach ≥ 5 rows ──────────────────
        print("5️⃣  Extra events to reach ≥5 rows …", end=" ", flush=True)
        extra_events = [
            _event("page_viewed", {"page": "login", "navigationType": "initial_load"}),
            _event(
                "supplier_status_changed",
                {
                    "supplier_id": 7,
                    "previous_status": "active",
                    "new_status": "suspended",
                    "country": "Spain",
                    "categories": ["carrier_last_mile"],
                },
            ),
        ]
        res = _post_batch(client, extra_events)
        assert res["stored"] == 2
        assert res["rejected"] == 0
        print(f"✅  stored={res['stored']}")

        # ── Verify total ≥ 5 ────────────────────────────────────────
        # We know from the batch results: 1+1+1+1+2 = 6 events stored.
        print(f"\n📊  Cumulative stored: 1+1+1+1+2 = 6 (≥ 5 ✅)")

        # ── 6. Mixed batch valid + invalid ──────────────────────────
        print("\n6️⃣  Mixed batch (valid + invalid) …", end=" ", flush=True)
        valid_event = _event(
            "login_succeeded",
            {"user_role": "admin"},
        )
        invalid_event = _event(
            "incident_created",
            {"incident_id": 1},  # missing required fields: category, origin, branch, status
        )
        # Remove the required event_type so it fails validation
        del invalid_event["event_type"]

        res = _post_batch(client, [valid_event, invalid_event])
        assert res["received"] == 2, f"Expected received=2, got {res}"
        assert res["stored"] == 1, f"Expected stored=1, got {res}"
        assert res["rejected"] == 1, f"Expected rejected=1, got {res}"
        print(f"✅  received={res['received']} stored={res['stored']} rejected={res['rejected']}")

        # ── Summary ─────────────────────────────────────────────────
        print()
        print("═" * 50)
        print("✅ ALL E2E TESTS PASSED")
        print("═" * 50)
        print()
        print("Scenarios covered:")
        print("  ✔ Technical event  (api_server_error)")
        print("  ✔ Business event   (incident_created)")
        print("  ✔ Inventory entry  (inbound_registered)")
        print("  ✔ Inventory exit   (outbound_registered)")
        print("  ✔ ≥5 rows stored   (6 total)")
        print("  ✔ Mixed batch      (valid stored, invalid rejected)")
        print()
        print("Response shape: {\"received\": N, \"stored\": M, \"rejected\": R}")


if __name__ == "__main__":
    run_e2e()