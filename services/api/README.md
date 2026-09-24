# TrackFlow API — `services/api`

FastAPI backend for the TrackFlow Supplier Directory. This service implements
**Milestone 5: Inventory Management with ORM & Dual Database**.

## Dual-database architecture

| Concern                                    | Store                              | Notes                                                             |
| ------------------------------------------ | ---------------------------------- | ----------------------------------------------------------------- |
| Users / auth                               | TinyDB                             | `data/suppliers.json`, tables `users`, `profiles`, `reset_tokens` |
| Profiles / suppliers                       | TinyDB                             | Existing tables — unchanged                                       |
| Incidents                                  | TinyDB                             | Existing table — unchanged                                        |
| **Inventory (SKU, StockEntry, StockExit)** | **SQLModel → PostgreSQL/Supabase** | Configured via `DATABASE_URL`                                     |

Users stay in TinyDB and remain the source of truth for authentication. Each
user has a stable `uuid` (backfilled on access for legacy rows) that is stored
on inventory movements as `user_uuid`. There is **no** User table in the
relational database.

## Setup

```bash
cd services/api
cp .env.example .env        # then fill in SECRET_KEY and (optionally) DATABASE_URL
uv sync                     # installs sqlmodel, psycopg2-binary, etc.
```

`DATABASE_URL` points at PostgreSQL (e.g. Supabase):

```
DATABASE_URL=postgresql://user:password@host:5432/postgres
```

If `DATABASE_URL` is unset, the app falls back to an in-memory SQLite engine
(for local dev / tests). Tables are created automatically at startup
(`SQLModel.metadata.create_all`).

## Inventory domain rules (canonical CONTEXT-trackflow)

- **`current_stock` is always computed, never stored.**
  `current_stock = SUM(StockEntry.quantity) − SUM(StockExit.quantity)` per SKU
  **per warehouse** (`LA` or `ZGZ`). A SKU in both warehouses has two separate
  stock figures.
- **Negative stock is rejected.** An outbound movement that would push stock
  below zero returns `HTTP 400`:
  `Insufficient stock for SKU '{sku}'. Available: {available}, requested: {quantity}.`
- **`tracking_number`** is required for `exit_type="dispatch"` and must be
  `null` for `exit_type="loss"`.
- Each SKU is tracked in exactly **one** warehouse; movements must use the
  SKU's own warehouse (a mismatch returns `HTTP 400`).
- `StockEntry.reference` and `StockExit.tracking_number` are realistic
  identifiers (`PO-2024-0098`, `GR-LA-0234`, `1Z999AA10123456784`).

## Routers

All `/inventory` routes require authentication (existing TinyDB JWT via
`get_current_user`):

| Method | Path                         | Description                             |
| ------ | ---------------------------- | --------------------------------------- |
| GET    | `/inventory/products`        | List SKUs with computed `current_stock` |
| POST   | `/inventory/products`        | Register a new SKU                      |
| GET    | `/inventory/products/{id}`   | Get one SKU with computed stock         |
| POST   | `/inventory/orders/inbound`  | Register a goods receipt (`StockEntry`) |
| POST   | `/inventory/orders/outbound` | Register a dispatch/loss (`StockExit`)  |
| GET    | `/inventory/orders`          | List all stock movements with SKU data  |

## Files

- `inventory_models.py` — **SQLModel ORM entities** `SKU`, `StockEntry`,
  `StockExit`. Intentionally separate from `models.py`: keep the ORM classes
  in `inventory_models.py` (do not move them into `models.py`).
- `models.py` — legacy/auth/application **Pydantic** models (users, profiles,
  suppliers, incidents) — not ORM, not touched by inventory.
- `schemas.py` — Pydantic create/response schemas (validation rules live here).
- `routers/inventory.py` — `/inventory` routes + computed-stock helpers +
  outbound row-lock + rollback-safe writes.
- `seed_inventory.py` — idempotent seed with the canonical 6 SKUs, 6 entries
  and 4 exits.
- `database.py` — TinyDB (unchanged) + lazy SQLModel engine / `get_db()`.

## Environment & database selection

- `DATABASE_URL` is read **at engine-build time** (not at import time), so a
  value supplied through `services/api/.env` is honoured — `main.py` calls
  `load_dotenv()` before the engine is ever requested.
- Resolution: `DATABASE_URL` → test-provided SQLite default → local dev
  SQLite fallback.
- **Production safety:** if `APP_ENV=production` and `DATABASE_URL` is
  missing (and `ALLOW_SQLITE_FALLBACK` is not explicitly truthy), startup
  raises instead of silently running on an in-memory SQLite database.
- Local development may run on in-memory SQLite by default (no DATABASE_URL,
  no APP_ENV=production); set `APP_ENV=production` on real deployments.
- `.env` stays ignored; `.env.example` has placeholder values only.

## Seed

```bash
uv run seed-inventory
# or
DATABASE_URL=postgresql://... uv run python -m seed_inventory
```

Re-running is safe (SKU-by-code, entry-by-reference, exit-by-tracking match).

## Tests

```bash
uv run --directory services/api pytest            # full suite (191 tests)
uv run --directory services/api pytest tests/test_inventory_api.py   # inventory
```

Inventory tests use SQLModel + in-memory SQLite (FK enforcement on,
`StaticPool`) with a `get_db` dependency override — no `DATABASE_URL` needed.
