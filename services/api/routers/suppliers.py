from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response, status
from tinydb.table import Document

from services.api.database import get_suppliers_table
from services.api.models import (
    Country,
    SupplierCreate,
    SupplierOut,
    SupplierRateUpdate,
    SupplierStatusUpdate,
    VALID_CATEGORIES,
)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def _timestamp_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _to_supplier_out(document: Document) -> SupplierOut:
    payload = dict(document)
    payload["id"] = int(document.doc_id)
    payload["updated_at"] = _parse_timestamp(payload["updated_at"])
    return SupplierOut(**payload)


@router.post("", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(supplier: SupplierCreate) -> SupplierOut:
    suppliers = get_suppliers_table()
    timestamp = _timestamp_now()
    payload = supplier.model_dump()
    payload["updated_at"] = timestamp
    doc_id = suppliers.insert(payload)
    stored = suppliers.get(doc_id=doc_id)
    if stored is None:
        raise HTTPException(status_code=500, detail="Supplier insert failed")
    return _to_supplier_out(stored)


@router.get("", response_model=list[SupplierOut])
def list_suppliers(country: Country | None = None, category: str | None = None) -> list[SupplierOut]:
    if category is not None and category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid category filter: {category}",
        )

    suppliers = get_suppliers_table()
    documents = suppliers.all()

    if country is not None:
        documents = [doc for doc in documents if doc.get("country") == country]
    if category is not None:
        documents = [doc for doc in documents if category in doc.get("categories", [])]

    return [_to_supplier_out(doc) for doc in documents]


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: int) -> SupplierOut:
    suppliers = get_suppliers_table()
    document = suppliers.get(doc_id=supplier_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return _to_supplier_out(document)


@router.patch("/{supplier_id}/rate", response_model=SupplierOut)
def update_supplier_rate(supplier_id: int, payload: SupplierRateUpdate) -> SupplierOut:
    suppliers = get_suppliers_table()
    document = suppliers.get(doc_id=supplier_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    suppliers.update(
        {
            "rate_per_shipment": payload.rate_per_shipment,
            "updated_at": _timestamp_now(),
        },
        doc_ids=[supplier_id],
    )
    updated_document = suppliers.get(doc_id=supplier_id)
    if updated_document is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return _to_supplier_out(updated_document)


@router.patch("/{supplier_id}/status", response_model=SupplierOut)
def update_supplier_status(supplier_id: int, payload: SupplierStatusUpdate) -> SupplierOut:
    suppliers = get_suppliers_table()
    document = suppliers.get(doc_id=supplier_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    suppliers.update({"status": payload.status}, doc_ids=[supplier_id])
    updated_document = suppliers.get(doc_id=supplier_id)
    if updated_document is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return _to_supplier_out(updated_document)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(supplier_id: int) -> Response:
    suppliers = get_suppliers_table()
    removed = suppliers.remove(doc_ids=[supplier_id])
    if not removed:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
