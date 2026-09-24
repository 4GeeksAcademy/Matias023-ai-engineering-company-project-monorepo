"""Idempotent inventory seed (Milestone 5 — ORM & Dual Database).

Seeds the SQL/relational inventory database (PostgreSQL/Supabase when
DATABASE_URL is set, SQLite otherwise) with the canonical TrackFlow rows from
``CONTEXT-trackflow.md``:

    * 6 SKUs  (3 x LA, 3 x ZGZ; fashion / electronics / cosmetics)
    * >= 4 StockEntries  (>= 2 for the same SKU in different quantities;
                           mixed warehouses; references like PO-2024-0098 /
                           GR-LA-0234 / GR-ZGZ-xxxx)
    * >= 3 StockExits    (>= 1 dispatch with a tracking_number like
                           "1Z999AA10123456784"; >= 1 loss with tracking null;
                           never exceeding the seeded entries per warehouse)

Idempotency:
    * SKUs are matched by their unique ``sku`` code.
    * Stock entries are matched by (sku, reference).
    * Stock exits are matched by (sku, tracking_number) for dispatches, or by
      (sku, exit_type='loss') for losses.
    Re-running the seed only ever inserts missing rows.

Usage:
    DATABASE_URL=postgresql://... uv run python -m seed_inventory
    uv run seed-inventory
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import Session, select

from database import get_engine
from inventory_models import SKU, StockEntry, StockExit, StockExitType


# ──────────────────────────────────────────────
# Production guard: fail loudly when DATABASE_URL
# is missing in a production environment.
# ──────────────────────────────────────────────
def _assert_production_ready() -> None:
    """Raise if APP_ENV=production and DATABASE_URL is not set."""
    database_url = os.environ.get("DATABASE_URL", "").strip()
    app_env = os.environ.get("APP_ENV", "").strip().lower()
    if app_env == "production" and not database_url:
        raise RuntimeError(
            "DATABASE_URL is required in a production environment but was not "
            "set. Configure DATABASE_URL (e.g. Supabase/PostgreSQL) before "
            "running the seed. To seed a local SQLite database, set "
            "APP_ENV=development or unset APP_ENV."
        )
    if not database_url:
        import warnings
        warnings.warn(
            "DATABASE_URL is not set — seeding the local SQLite database. "
            "Set DATABASE_URL to target a real PostgreSQL/Supabase instance."
        )


# A documented sentinel for seeded movements. In normal operation each
# movement stores the real TinyDB user UUID from the authenticated operative;
# seed rows are not linked to a real TinyDB user, so they use this marker.
SEED_USER_UUID = "00000000-0000-0000-0000-000000000000"

SKU_SEED = [
    {
        "name": "Classic White Sneaker - Size 42",
        "sku": "CLT-SNK-W-42",
        "client_name": "PureStep Footwear",
        "category": "fashion",
        "warehouse": "LA",
    },
    {
        "name": "Classic White Sneaker - Size 42",
        "sku": "CLT-SNK-W-42-Z",
        "client_name": "PureStep Footwear",
        "category": "fashion",
        "warehouse": "ZGZ",
    },
    {
        "name": "Wireless Earbuds Pro",
        "sku": "TEC-EAR-001",
        "client_name": "SoundWave Electronics",
        "category": "electronics",
        "warehouse": "LA",
    },
    {
        "name": "Hydrating Face Serum 30ml",
        "sku": "CSM-SRM-030",
        "client_name": "GlowLab Cosmetics",
        "category": "cosmetics",
        "warehouse": "ZGZ",
    },
    {
        "name": "Slim Fit Chino - Navy 32/32",
        "sku": "CLT-CHN-N-32",
        "client_name": "UrbanThread",
        "category": "fashion",
        "warehouse": "LA",
    },
    {
        "name": "USB-C Fast Charger 65W",
        "sku": "TEC-CHG-065",
        "client_name": "SoundWave Electronics",
        "category": "electronics",
        "warehouse": "ZGZ",
    },
]

# Entries reference SKUs by their `sku` code. At least two entries target the
# same SKU (`CLT-SNK-W-42`) with different quantities, with a mix of LA + ZGZ.
ENTRY_SEED = [
    # Two receipts for the same SKU in different quantities.
    {"sku": "CLT-SNK-W-42", "quantity": 500, "reference": "GR-LA-0234", "warehouse": "LA"},
    {"sku": "CLT-SNK-W-42", "quantity": 120, "reference": "PO-2024-0098", "warehouse": "LA"},
    {"sku": "TEC-EAR-001", "quantity": 300, "reference": "GR-LA-0235", "warehouse": "LA"},
    {"sku": "CSM-SRM-030", "quantity": 480, "reference": "PO-2024-0102", "warehouse": "ZGZ"},
    {"sku": "CLT-CHN-N-32", "quantity": 250, "reference": "GR-LA-0237", "warehouse": "LA"},
    {"sku": "TEC-CHG-065", "quantity": 400, "reference": "GR-ZGZ-0003", "warehouse": "ZGZ"},
]

# Exits reference SKUs by `sku` code. Quantities never exceed the seeded
# entries for the same SKU + warehouse.
EXIT_SEED = [
    {
        "sku": "CLT-SNK-W-42",
        "quantity": 45,
        "exit_type": "dispatch",
        "tracking_number": "1Z999AA10123456784",
        "warehouse": "LA",
    },
    {
        "sku": "TEC-EAR-001",
        "quantity": 12,
        "exit_type": "dispatch",
        "tracking_number": "1Z999AA10123456785",
        "warehouse": "LA",
    },
    {
        "sku": "CSM-SRM-030",
        "quantity": 8,
        "exit_type": "loss",
        "tracking_number": None,
        "warehouse": "ZGZ",
    },
    {
        "sku": "CLT-CHN-N-32",
        "quantity": 30,
        "exit_type": "dispatch",
        "tracking_number": "1Z999AA10123456786",
        "warehouse": "LA",
    },
]


def _now() -> datetime:
    """Return a tz-aware UTC datetime (matches inventory model defaults)."""
    return datetime.now(timezone.utc)


def main() -> int:
    try:
        # Load .env when run directly (python -m seed_inventory,
        # uv run seed-inventory) so DATABASE_URL is visible.
        load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

        _assert_production_ready()
        from database import init_db

        init_db()
        engine = get_engine()

        with Session(engine) as session:
            sku_by_code: dict[str, SKU] = {}

            inserted_skus = 0
            for raw in SKU_SEED:
                existing = session.exec(
                    select(SKU).where(SKU.sku == raw["sku"])
                ).first()
                if existing is not None:
                    sku_by_code[raw["sku"]] = existing
                    continue
                sku = SKU(**raw)
                session.add(sku)
                session.flush()
                sku_by_code[raw["sku"]] = sku
                inserted_skus += 1
            session.commit()

            inserted_entries = 0
            for raw in ENTRY_SEED:
                sku = sku_by_code[raw["sku"]]
                already = session.exec(
                    select(StockEntry).where(
                        StockEntry.sku_id == sku.id,
                        StockEntry.reference == raw["reference"],
                    )
                ).first()
                if already is not None:
                    continue
                session.add(
                    StockEntry(
                        sku_id=sku.id,
                        quantity=raw["quantity"],
                        reference=raw["reference"],
                        warehouse=raw["warehouse"],
                        user_uuid=SEED_USER_UUID,
                        created_at=_now(),
                    )
                )
                inserted_entries += 1
            session.commit()

            inserted_exits = 0
            for raw in EXIT_SEED:
                sku = sku_by_code[raw["sku"]]
                if raw["exit_type"] == "dispatch":
                    already = session.exec(
                        select(StockExit).where(
                            StockExit.sku_id == sku.id,
                            StockExit.tracking_number == raw["tracking_number"],
                        )
                    ).first()
                else:  # loss
                    already = session.exec(
                        select(StockExit).where(
                            StockExit.sku_id == sku.id,
                            StockExit.exit_type == StockExitType.LOSS,
                        )
                    ).first()
                if already is not None:
                    continue
                session.add(
                    StockExit(
                        sku_id=sku.id,
                        quantity=raw["quantity"],
                        exit_type=raw["exit_type"],
                        tracking_number=raw["tracking_number"],
                        warehouse=raw["warehouse"],
                        user_uuid=SEED_USER_UUID,
                        created_at=_now(),
                    )
                )
                inserted_exits += 1
            session.commit()

        print(f"Inserted SKUs: {inserted_skus}")
        print(f"Inserted stock entries: {inserted_entries}")
        print(f"Inserted stock exits: {inserted_exits}")
        print(f"Total SKUs in database: {len(sku_by_code)}")
        return 0
    except (OSError, IOError) as exc:
        print(f"Database error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())