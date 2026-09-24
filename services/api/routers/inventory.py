"""Inventory API router (Milestone 5 — ORM & Dual Database).

All routes are protected by the existing TinyDB auth layer via
``Depends(get_current_user)``.

Routes (canonical TrackFlow):
    * GET    /inventory/products          -> list SKUs (with computed stock)
    * POST   /inventory/products          -> create a SKU
    * GET    /inventory/products/{id}     -> single SKU (with computed stock)
    * POST   /inventory/orders/inbound    -> register a StockEntry
    * POST   /inventory/orders/outbound   -> register a StockExit
    * GET    /inventory/orders            -> list movements (entries + exits)
    * (GET)  /inventory/orders/{id}       -> single movement (ordered by id)

Stock semantics:
    * ``current_stock`` is NEVER stored; it is computed as
      SUM(entries.quantity) - SUM(exits.quantity) per SKU *and* warehouse.
    * An outbound movement that would drive stock below zero for that
      SKU+warehouse combination is rejected with HTTP 400 and the EXACT
      message from the canonical context:
        "Insufficient stock for SKU '{sku}'. Available: {available}, requested: {quantity}."
    * ``user_uuid`` on movements records the authenticated TinyDB user's UUID.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, func, select

from database import get_db
from inventory_models import (
    SKU,
    StockEntry,
    StockExit,
    StockExitType,
)
from schemas import (
    SKUCreate,
    SKUResponse,
    StockEntryCreate,
    StockEntryResponse,
    StockExitCreate,
    StockExitResponse,
    StockMovementResponse,
)
from security import get_current_user
from models import UserResponse


router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"],
    dependencies=[Depends(get_current_user)],
)


# ──────────────────────────────────────────────
# Stock computation helpers
# ──────────────────────────────────────────────


def _stock_for_sku(session: Session, sku_id: int, warehouse: str) -> int:
    """Compute current stock for a SKU in a given warehouse.

    current_stock = SUM(entries.quantity) - SUM(exits.quantity)
    """
    entry_sum = session.exec(
        select(func.coalesce(func.sum(StockEntry.quantity), 0)).where(
            StockEntry.sku_id == sku_id,
            StockEntry.warehouse == warehouse,
        )
    ).one()

    exit_sum = session.exec(
        select(func.coalesce(func.sum(StockExit.quantity), 0)).where(
            StockExit.sku_id == sku_id,
            StockExit.warehouse == warehouse,
        )
    ).one()

    return int(entry_sum) - int(exit_sum)


def _ensure_warehouse_matches_sku(sku: SKU, warehouse) -> None:
    """Validate a movement's warehouse matches its SKU's warehouse.

    Each SKU is tracked in exactly one warehouse (LA or ZGZ). Requiring the
    movement to use the same warehouse keeps stock per SKU+warehouse
    unambiguous and avoids invisible cross-warehouse stock.
    """
    if warehouse != sku.warehouse:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Warehouse mismatch: SKU '{sku.sku}' belongs to "
                f"warehouse '{sku.warehouse.value}', got '{warehouse.value}'."
            ),
        )


def _sku_response(session: Session, sku: SKU) -> SKUResponse:
    return SKUResponse(
        id=sku.id,
        name=sku.name,
        sku=sku.sku,
        client_name=sku.client_name,
        category=sku.category,
        warehouse=sku.warehouse,
        current_stock=_stock_for_sku(session, sku.id, sku.warehouse.value),
        created_at=sku.created_at,
    )


def _get_sku_or_404(session: Session, sku_id: int) -> SKU:
    sku = session.get(SKU, sku_id)
    if sku is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU with id {sku_id} not found",
        )
    return sku


def _get_sku_for_update_or_404(session: Session, sku_id: int) -> SKU:
    """Fetch a SKU with a ``SELECT ... FOR UPDATE`` row lock.

    Used by the outbound handler so concurrent requests serialise on the SKU
    row (PostgreSQL): the second transaction blocks until the first commits/
    rolls back, then sees the up-to-date stock. This prevents two simultaneous
    outbound requests both reading stale available stock and overselling.
    SQLite ignores the locking pragma, which is acceptable here — the lock is
    meaningful against PostgreSQL/Supabase in production.
    """
    sku = session.exec(
        select(SKU).where(SKU.id == sku_id).with_for_update()
    ).first()
    if sku is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU with id {sku_id} not found",
        )
    return sku


# ──────────────────────────────────────────────
# Products
# ──────────────────────────────────────────────


@router.get(
    "/products",
    response_model=list[SKUResponse],
)
def list_products(
    session: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    skus = session.exec(select(SKU).order_by(SKU.id)).all()

    return [_sku_response(session, sku) for sku in skus]


@router.post(
    "/products",
    response_model=SKUResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    payload: SKUCreate,
    session: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    existing = session.exec(select(SKU).where(SKU.sku == payload.sku)).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"SKU '{payload.sku}' already exists",
        )

    sku = SKU(
        name=payload.name,
        sku=payload.sku,
        client_name=payload.client_name,
        category=payload.category,
        warehouse=payload.warehouse,
    )
    session.add(sku)
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    session.refresh(sku)

    return _sku_response(session, sku)


@router.get(
    "/products/{sku_id}",
    response_model=SKUResponse,
)
def get_product(
    sku_id: int,
    session: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    sku = _get_sku_or_404(session, sku_id)

    return _sku_response(session, sku)


# ──────────────────────────────────────────────
# Orders (inbound / outbound)
# ──────────────────────────────────────────────


@router.post(
    "/orders/inbound",
    response_model=StockEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_inbound_order(
    payload: StockEntryCreate,
    session: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    sku = _get_sku_or_404(session, payload.sku_id)
    _ensure_warehouse_matches_sku(sku, payload.warehouse)

    entry = StockEntry(
        sku_id=sku.id,
        quantity=payload.quantity,
        reference=payload.reference,
        warehouse=payload.warehouse,
        user_uuid=current_user.uuid or "",
    )
    session.add(entry)
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    session.refresh(entry)

    return StockEntryResponse(
        id=entry.id,
        sku_id=entry.sku_id,
        quantity=entry.quantity,
        reference=entry.reference,
        warehouse=entry.warehouse,
        created_at=entry.created_at,
        user_uuid=entry.user_uuid,
    )


@router.post(
    "/orders/outbound",
    response_model=StockExitResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_outbound_order(
    payload: StockExitCreate,
    session: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    sku = _get_sku_for_update_or_404(session, payload.sku_id)
    _ensure_warehouse_matches_sku(sku, payload.warehouse)

    # Negative-stock guard: compute available AFTER the row lock is acquired
    # (PostgreSQL: no concurrent outbound can mutate this SKU's stock while we
    # hold the lock) and BEFORE registering any exit. Reject with the EXACT
    # canonical message.
    available = _stock_for_sku(session, sku.id, payload.warehouse.value)

    if available < payload.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Insufficient stock for SKU '{sku.sku}'. "
                f"Available: {available}, requested: {payload.quantity}."
            ),
        )

    exit_movement = StockExit(
        sku_id=sku.id,
        quantity=payload.quantity,
        exit_type=payload.exit_type,
        tracking_number=(
            payload.tracking_number.strip()
            if payload.tracking_number is not None
            else None
        ),
        warehouse=payload.warehouse,
        user_uuid=current_user.uuid or "",
    )
    session.add(exit_movement)
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    session.refresh(exit_movement)

    return StockExitResponse(
        id=exit_movement.id,
        sku_id=exit_movement.sku_id,
        quantity=exit_movement.quantity,
        exit_type=exit_movement.exit_type,
        tracking_number=exit_movement.tracking_number,
        warehouse=exit_movement.warehouse,
        created_at=exit_movement.created_at,
        user_uuid=exit_movement.user_uuid,
    )


@router.get(
    "/orders",
    response_model=list[StockMovementResponse],
)
def list_orders(
    session: Session = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    """List all stock movements (entries and exits) with SKU context.

    Avoids N+1 by loading the SKU rows for all referenced sku_ids in one query.
    """
    entries = session.exec(
        select(StockEntry).order_by(StockEntry.id)
    ).all()
    exits = session.exec(
        select(StockExit).order_by(StockExit.id)
    ).all()

    sku_ids = {e.sku_id for e in entries} | {e.sku_id for e in exits}
    skus = {}
    if sku_ids:
        sku_rows = session.exec(select(SKU).where(SKU.id.in_(sku_ids))).all()
        skus = {sku.id: sku for sku in sku_rows}

    movements: list[StockMovementResponse] = []

    for entry in entries:
        sku = skus.get(entry.sku_id)
        movements.append(
            StockMovementResponse(
                id=entry.id,
                kind="entry",
                sku_id=entry.sku_id,
                sku=sku.sku if sku else "",
                sku_name=sku.name if sku else "",
                warehouse=entry.warehouse,
                quantity=entry.quantity,
                reference=entry.reference,
                exit_type=None,
                tracking_number=None,
                user_uuid=entry.user_uuid,
                created_at=entry.created_at,
            )
        )

    for exit_movement in exits:
        sku = skus.get(exit_movement.sku_id)
        movements.append(
            StockMovementResponse(
                id=exit_movement.id,
                kind="exit",
                sku_id=exit_movement.sku_id,
                sku=sku.sku if sku else "",
                sku_name=sku.name if sku else "",
                warehouse=exit_movement.warehouse,
                quantity=exit_movement.quantity,
                reference=None,
                exit_type=exit_movement.exit_type,
                tracking_number=exit_movement.tracking_number,
                user_uuid=exit_movement.user_uuid,
                created_at=exit_movement.created_at,
            )
        )

    movements.sort(key=lambda m: m.id)
    return movements