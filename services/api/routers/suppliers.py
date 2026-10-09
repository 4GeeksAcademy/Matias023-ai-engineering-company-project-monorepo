from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from tinydb import Query

from cache import (
    cache,
    SUPPLIER_CACHE_NAMESPACE,
    SUPPLIER_LIST_TTL_SECONDS as _LIST_TTL,
    SUPPLIER_DETAIL_TTL_SECONDS as _DETAIL_TTL,
)
from database import document_to_dict, suppliers_table
from models import (
    Country,
    SupplierCategory,
    SupplierCreate,
    SupplierRateUpdate,
    SupplierResponse,
    SupplierStatusUpdate,
)
from security import get_current_user


router = APIRouter(
    prefix="/suppliers",
    tags=["Suppliers"],
    dependencies=[Depends(get_current_user)],
)


def _supplier_list_cache_key(
    country: Country | None,
    category: SupplierCategory | None,
) -> str:
    """Deterministic cache key for supplier list queries.

    Query parameters are included in sorted, normalised order so that
    different filter combinations produce distinct keys while the same
    combination always produces the same key.
    """
    parts = ["suppliers:list"]
    if country is not None:
        parts.append(f"country={country}")
    if category is not None:
        parts.append(f"category={category}")
    return ":".join(parts) if len(parts) > 1 else "suppliers:list"


def _supplier_detail_cache_key(supplier_id: int) -> str:
    return f"suppliers:detail:{supplier_id}"


def get_supplier_or_404(supplier_id: int):
    supplier = suppliers_table.get(doc_id=supplier_id)

    if supplier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found",
        )

    return supplier


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier(payload: SupplierCreate):
    record = payload.model_dump()
    record["updated_at"] = datetime.now(timezone.utc).isoformat()

    supplier_id = suppliers_table.insert(record)
    supplier = suppliers_table.get(doc_id=supplier_id)

    # New supplier affects list output → invalidate entire supplier namespace
    cache.invalidate_prefix(SUPPLIER_CACHE_NAMESPACE)

    return document_to_dict(supplier)


@router.get(
    "",
    response_model=list[SupplierResponse],
)
def list_suppliers(
    country: Country | None = None,
    category: SupplierCategory | None = None,
):
    # Auth dependency already executed via router-level Depends.
    # Cache key encodes ALL query params in deterministic order.
    cache_key = _supplier_list_cache_key(country, category)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    supplier_query = Query()

    if country is not None and category is not None:
        documents = suppliers_table.search(
            (supplier_query.country == country)
            & supplier_query.categories.any([category])
        )
    elif country is not None:
        documents = suppliers_table.search(
            supplier_query.country == country
        )
    elif category is not None:
        documents = suppliers_table.search(
            supplier_query.categories.any([category])
        )
    else:
        documents = suppliers_table.all()

    result = [
        document_to_dict(document)
        for document in documents
    ]

    cache.set(cache_key, result, ttl=_LIST_TTL)
    return result


@router.get(
    "/{supplier_id}",
    response_model=SupplierResponse,
)
def get_supplier(supplier_id: int):
    # Auth dependency already executed via router-level Depends.
    cache_key = _supplier_detail_cache_key(supplier_id)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    supplier = get_supplier_or_404(supplier_id)

    result = document_to_dict(supplier)
    cache.set(cache_key, result, ttl=_DETAIL_TTL)
    return result


@router.patch(
    "/{supplier_id}/rate",
    response_model=SupplierResponse,
)
def update_supplier_rate(
    supplier_id: int,
    payload: SupplierRateUpdate,
):
    get_supplier_or_404(supplier_id)

    suppliers_table.update(
        {
            "rate_per_shipment": payload.rate_per_shipment,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        doc_ids=[supplier_id],
    )

    supplier = get_supplier_or_404(supplier_id)

    # Rate change affects list ordering/values and detail → invalidate all
    cache.invalidate_prefix(SUPPLIER_CACHE_NAMESPACE)

    return document_to_dict(supplier)


@router.patch(
    "/{supplier_id}/status",
    response_model=SupplierResponse,
)
def update_supplier_status(
    supplier_id: int,
    payload: SupplierStatusUpdate,
):
    get_supplier_or_404(supplier_id)

    suppliers_table.update(
        {
            "status": payload.status,
        },
        doc_ids=[supplier_id],
    )

    supplier = get_supplier_or_404(supplier_id)

    # Status change affects list visibility and detail → invalidate all
    cache.invalidate_prefix(SUPPLIER_CACHE_NAMESPACE)

    return document_to_dict(supplier)


@router.delete(
    "/{supplier_id}",
    response_model=SupplierResponse,
)
def delete_supplier(supplier_id: int):
    supplier = get_supplier_or_404(supplier_id)

    response = document_to_dict(supplier)

    suppliers_table.remove(
        doc_ids=[supplier_id],
    )

    # Deletion changes list output → invalidate all
    cache.invalidate_prefix(SUPPLIER_CACHE_NAMESPACE)

    return response
