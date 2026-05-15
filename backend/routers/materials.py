"""
OrderHub CRM — Materials Router

MAT-1: CRUD for direct materials catalog. Soft-delete via `is_active=False`.
MAT-2: Receipts + ledger + adjustments. Receipts trigger weighted-average
       recompute via material_stock_service.apply_receipt; adjustments append
       a MaterialMovement via apply_movement. Caller (this router) owns the
       commit boundary so receipt insert + movement insert + Material update
       all land in a single transaction.
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.material import (
    Material,
    MaterialMovement,
    MaterialMovementReason,
    MaterialReceipt,
)
from models.order import Order
from models.user import UserRole
from routers.dependencies import require_role
from schemas.material import (
    MaterialCreate,
    MaterialMovementRead,
    MaterialRead,
    MaterialReceiptCreate,
    MaterialReceiptRead,
    MaterialReceiptResponse,
    MaterialStockAdjustment,
    MaterialUpdate,
)
from services import material_stock_service


router = APIRouter(prefix="/api/materials", tags=["Materials"])


@router.get("", response_model=List[MaterialRead])
async def list_materials(
    search: str | None = Query(None, max_length=200),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    stmt = select(Material).order_by(Material.name)
    if not include_inactive:
        stmt = stmt.where(Material.is_active == True)  # noqa: E712
    if search:
        stmt = stmt.where(Material.name.ilike(f"%{search}%"))
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=MaterialRead, status_code=status.HTTP_201_CREATED)
async def create_material(
    body: MaterialCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    material = Material(
        name=body.name,
        unit=body.unit,
        currency=body.currency,
        supplier_name=body.supplier_name,
        notes=body.notes,
    )
    db.add(material)
    await db.flush()
    await db.refresh(material)
    await db.commit()
    return material


@router.get("/{material_id}", response_model=MaterialRead)
async def get_material(
    material_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    material = await db.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")
    return material


@router.patch("/{material_id}", response_model=MaterialRead)
async def update_material(
    material_id: uuid.UUID,
    body: MaterialUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    material = await db.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")

    payload = body.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(material, key, value)

    await db.flush()
    await db.refresh(material)
    await db.commit()
    return material


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_material(
    material_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    material = await db.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")
    material.is_active = False
    await db.commit()


# ---- MAT-2: Receipts, ledger, adjustments ----


@router.post(
    "/{material_id}/receipts",
    response_model=MaterialReceiptResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_material_receipt(
    material_id: uuid.UUID,
    body: MaterialReceiptCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    """Register a direct-material purchase. Single transaction:
       receipt insert → weighted-avg recompute → movement insert → stock update.
    """
    material = await db.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")

    receipt = await material_stock_service.apply_receipt(
        db,
        material=material,
        qty=body.qty,
        unit_cost=body.unit_cost,
        currency=body.currency,
        shipping_cost=body.shipping_cost,
        supplier=body.supplier,
        invoice_no=body.invoice_no,
        received_at=body.received_at,
        notes=body.notes,
        is_initial=False,
        user_id=user.id,
    )
    await db.commit()
    await db.refresh(material)
    await db.refresh(receipt)
    return MaterialReceiptResponse(
        material=MaterialRead.model_validate(material),
        receipt=MaterialReceiptRead.model_validate(receipt),
    )


@router.get(
    "/{material_id}/receipts",
    response_model=List[MaterialReceiptRead],
)
async def list_material_receipts(
    material_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    material = await db.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")

    offset = (page - 1) * limit
    stmt = (
        select(MaterialReceipt)
        .where(MaterialReceipt.material_id == material_id)
        .order_by(MaterialReceipt.received_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get(
    "/{material_id}/movements",
    response_model=List[MaterialMovementRead],
)
async def list_material_movements(
    material_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    reason: Optional[MaterialMovementReason] = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    material = await db.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")

    offset = (page - 1) * limit
    stmt = (
        select(MaterialMovement, Order.external_id)
        .outerjoin(Order, MaterialMovement.order_id == Order.id)
        .where(MaterialMovement.material_id == material_id)
        .order_by(MaterialMovement.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if reason is not None:
        stmt = stmt.where(MaterialMovement.reason == reason)
    result = await db.execute(stmt)
    movements = []
    for movement, external_id in result.all():
        movement.order_code = f"#{external_id}" if external_id else None
        movements.append(movement)
    return movements


@router.post(
    "/{material_id}/adjust",
    response_model=MaterialRead,
)
async def adjust_material_stock(
    material_id: uuid.UUID,
    body: MaterialStockAdjustment,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    """Manual stock adjustment — emits a single MaterialMovement with the
    chosen reason (`waste` or `adjustment`). Permissive race policy per
    PKG-2 — counter may go negative, operator restocks subsequently.
    """
    material = await db.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found")

    reason = (
        MaterialMovementReason.WASTE
        if body.reason == "waste"
        else MaterialMovementReason.ADJUSTMENT
    )
    await material_stock_service.apply_movement(
        db,
        material_id=material_id,
        delta=body.delta,
        reason=reason,
        user_id=user.id,
        notes=body.notes,
    )
    await db.commit()
    await db.refresh(material)
    return material
