from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

VALID_COUNTRIES = ("USA", "Spain")
VALID_CATEGORIES = (
    "carrier_last_mile",
    "carrier_international",
    "warehouse_supplies",
    "packaging_materials",
    "reverse_logistics",
    "fleet_maintenance",
    "it_and_wms_software",
    "cleaning_and_facilities",
)
VALID_STATUSES = ("active", "suspended")
COUNTRY_TO_CURRENCY = {"USA": "USD", "Spain": "EUR"}

Country = Literal["USA", "Spain"]
Currency = Literal["USD", "EUR"]
Status = Literal["active", "suspended"]


class SupplierBase(BaseModel):
    name: str = Field(min_length=1)
    country: Country
    categories: list[str] = Field(min_length=1)
    rate_per_shipment: float = Field(gt=0)
    currency: Currency
    status: Status
    service_zone: str | None = None
    contact_email: str | None = None
    notes: str | None = None

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, categories: list[str]) -> list[str]:
        invalid_categories = [c for c in categories if c not in VALID_CATEGORIES]
        if invalid_categories:
            allowed = ", ".join(VALID_CATEGORIES)
            raise ValueError(
                "Invalid categories: "
                + ", ".join(invalid_categories)
                + f". Allowed categories: {allowed}"
            )
        return categories

    @model_validator(mode="after")
    def validate_country_currency(self) -> "SupplierBase":
        expected_currency = COUNTRY_TO_CURRENCY[self.country]
        if self.currency != expected_currency:
            raise ValueError(
                f"Currency must be {expected_currency} when country is {self.country}"
            )
        return self


class SupplierCreate(SupplierBase):
    pass


class SupplierOut(SupplierBase):
    id: int
    updated_at: datetime


class SupplierRateUpdate(BaseModel):
    rate_per_shipment: float = Field(gt=0)


class SupplierStatusUpdate(BaseModel):
    status: Status
