"""Inventory ORM models (Milestone 5 — ORM & Dual Database).

These SQLModel classes are intentionally kept in a separate module from the
legacy Pydantic models in ``models.py``.

Why:
-----
* ``models.py`` contains TinyDB-oriented Pydantic request/response models for
  suppliers, users, profiles, auth and incidents. Those must not be disturbed.
* Inventory lives in a *relational* database (PostgreSQL/Supabase) driven by
  SQLModel. Mixing SQLModel table classes into models.py would make that file
  import SQLAlchemy, increase coupling, and risk destabilising existing
  endpoints and tests.
* Keeping a single ``inventory_models.py`` mirrors the canonical TrackFlow
  layout (``services/.../models.py`` for inventory ORM models) while isolating
  the new dependency surface.

Design decisions (from the canonical CONTEXT-trackflow.md):
-----------------------------------------------------------
* ``SKU.id`` is an integer primary key.
* ``current_stock`` is NEVER stored on SKU; it is always computed as
  SUM(StockEntry.quantity) - SUM(StockExit.quantity) *per SKU *per warehouse*.
* ``StockEntry`` and ``StockExit`` reference ``SKU.id`` via a foreign key.
* ``warehouse`` is one of ``LA`` (Los Angeles) or ``ZGZ`` (Zaragoza). Both
  warehouses share the same tables; stock is tracked per SKU *and* warehouse.
* ``StockExit.tracking_number`` is REQUIRED for ``exit_type="dispatch"`` and
  MUST be null for ``exit_type="loss"`` (enforced in schemas + router, not in
  the DB).
* ``user_uuid`` is a plain string that stores the authenticated TinyDB user's
  UUID. There is deliberately NO User table here: users stay in TinyDB and the
  inventory database never owns identity.
"""

from datetime import datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    """Return a timezone-aware UTC datetime.

    SQLModel's default ``DateTime`` column requires tz-aware values; legacy
    users and seed data agree on UTC.
    """
    return datetime.now(timezone.utc)


class Warehouse(str, Enum):
    """Warehouses for TrackFlow. Both share the same tables."""

    LA = "LA"
    ZGZ = "ZGZ"


class Category(str, Enum):
    """Product categories allowed for SKUs."""

    FASHION = "fashion"
    ELECTRONICS = "electronics"
    COSMETICS = "cosmetics"


class StockExitType(str, Enum):
    """Types of outbound stock movement."""

    DISPATCH = "dispatch"
    LOSS = "loss"


class SKU(SQLModel, table=True):
    """A sellable product tracked across one or more warehouses.

    ``current_stock`` is NOT a column. It is computed on read as
    SUM(entries.quantity) - SUM(exits.quantity) for the matching warehouse.
    """

    __tablename__ = "skus"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    sku: str = Field(index=True, unique=True)
    client_name: str
    category: Category
    warehouse: Warehouse

    created_at: datetime = Field(default_factory=_utcnow)


class StockEntry(SQLModel, table=True):
    """An inbound stock movement for a SKU in a single warehouse."""

    __tablename__ = "stock_entries"

    id: int | None = Field(default=None, primary_key=True)
    sku_id: int = Field(foreign_key="skus.id", index=True)
    quantity: int
    reference: str
    warehouse: Warehouse
    created_at: datetime = Field(default_factory=_utcnow)
    user_uuid: str


class StockExit(SQLModel, table=True):
    """An outbound stock movement (dispatch or loss).

    ``tracking_number`` is required for ``exit_type="dispatch"`` and must be
    null for ``exit_type="loss"`` (validated in schemas + router).
    """

    __tablename__ = "stock_exits"

    id: int | None = Field(default=None, primary_key=True)
    sku_id: int = Field(foreign_key="skus.id", index=True)
    quantity: int
    exit_type: StockExitType
    tracking_number: str | None = None
    warehouse: Warehouse
    created_at: datetime = Field(default_factory=_utcnow)
    user_uuid: str