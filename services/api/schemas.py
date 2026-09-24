"""Inventory request/response schemas (Milestone 5).

Validation rules implemented here:

* ``quantity`` must be a positive integer for both entries and exits.
* ``warehouse`` and ``category`` are validated against the enum values.
* ``current_stock`` is a **response-only** computed field — it is never
  accepted on create schemas.
* ``StockExitCreate`` enforces the tracking number rules:
    - ``exit_type == "dispatch"`` -> ``tracking_number`` REQUIRED
    - ``exit_type == "loss"``     -> ``tracking_number`` MUST be None
* ``SKUResponse`` exposes the computed ``current_stock`` for a given
  SKU+warehouse; ``id`` is always required in responses.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from inventory_models import Category, StockExitType, Warehouse


# ──────────────────────────────────────────────
# SKU
# ──────────────────────────────────────────────


class SKUCreate(BaseModel):
    name: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    client_name: str = Field(min_length=1)
    category: Category
    warehouse: Warehouse

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("sku must not be empty")
        return value


class SKUResponse(BaseModel):
    id: int
    name: str
    sku: str
    client_name: str
    category: Category
    warehouse: Warehouse
    # Computed on read — never stored.
    current_stock: int
    created_at: datetime


# ──────────────────────────────────────────────
# Stock movements (inbound)
# ──────────────────────────────────────────────


class StockEntryCreate(BaseModel):
    sku_id: int
    quantity: int = Field(gt=0)
    reference: str = Field(min_length=1)
    warehouse: Warehouse

    @field_validator("reference")
    @classmethod
    def normalize_reference(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reference must not be empty")
        return value


class StockEntryResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    reference: str
    warehouse: Warehouse
    created_at: datetime
    user_uuid: str


# ──────────────────────────────────────────────
# Stock movements (outbound)
# ──────────────────────────────────────────────


class StockExitCreate(BaseModel):
    sku_id: int
    quantity: int = Field(gt=0)
    exit_type: StockExitType
    tracking_number: str | None = None
    warehouse: Warehouse

    @model_validator(mode="after")
    def validate_tracking_number(self) -> "StockExitCreate":
        if self.exit_type == StockExitType.DISPATCH:
            if not self.tracking_number or not self.tracking_number.strip():
                raise ValueError(
                    "tracking_number is required for exit_type 'dispatch'"
                )
        else:  # loss
            if self.tracking_number is not None:
                raise ValueError(
                    "tracking_number must be null for exit_type 'loss'"
                )
        return self


class StockExitResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    exit_type: StockExitType
    tracking_number: str | None = None
    warehouse: Warehouse
    created_at: datetime
    user_uuid: str


# ──────────────────────────────────────────────
# Order / movement listing (GET /inventory/orders)
# ──────────────────────────────────────────────


class StockMovementResponse(BaseModel):
    """A single movement (entry or exit) with SKU context for the orders feed."""

    id: int
    kind: str  # "entry" | "exit"
    sku_id: int
    sku: str
    sku_name: str
    warehouse: Warehouse
    quantity: int
    reference: str | None = None
    exit_type: StockExitType | None = None
    tracking_number: str | None = None
    user_uuid: str
    created_at: datetime