"""
OrderHub CRM — Overhead Materials Router

MAT-1: CRUD for indirect/consumable materials catalog.
MAT-2: Receipt expense events — `OverheadMaterialReceipt` rows with optional
       shop_id for per-shop attribution (or NULL for global overhead). No
       ledger, no stock — just records the financial fact for FIN-1
       integration in MAT-5.
"""

import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.material import OverheadMaterial, OverheadMaterialReceipt
from models.shop import Shop
from models.user import Capability, UserRole
from routers.dependencies import require_capability, require_role
from services.access_service import get_shop_scope
from schemas.material import (
    OverheadMaterialCreate,
    OverheadMaterialRead,
    OverheadMaterialReceiptCreate,
    OverheadMaterialReceiptRead,
    OverheadMaterialUpdate,
)


# USER-ACCESS-2: overhead materials + receipts expose unit/total costs — an
# itemised cost surface, gated by view_costs at the router level (on top of the
# per-endpoint OWNER/MANAGER role gate).
router = APIRouter(
    prefix="/api/overhead-materials",
    tags=["Overhead Materials"],
    dependencies=[Depends(require_capability(Capability.VIEW_COSTS))],
)


@router.get("", response_model=List[OverheadMaterialRead])
async def list_overhead_materials(
    search: str | None = Query(None, max_length=200),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    stmt = select(OverheadMaterial).order_by(OverheadMaterial.name)
    if not include_inactive:
        stmt = stmt.where(OverheadMaterial.is_active == True)  # noqa: E712
    if search:
        stmt = stmt.where(OverheadMaterial.name.ilike(f"%{search}%"))
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=OverheadMaterialRead, status_code=status.HTTP_201_CREATED)
async def create_overhead_material(
    body: OverheadMaterialCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    overhead = OverheadMaterial(
        name=body.name,
        unit=body.unit,
        notes=body.notes,
    )
    db.add(overhead)
    await db.flush()
    await db.refresh(overhead)
    await db.commit()
    return overhead


@router.get("/{overhead_id}", response_model=OverheadMaterialRead)
async def get_overhead_material(
    overhead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    overhead = await db.get(OverheadMaterial, overhead_id)
    if overhead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Overhead material not found"
        )
    return overhead


@router.patch("/{overhead_id}", response_model=OverheadMaterialRead)
async def update_overhead_material(
    overhead_id: uuid.UUID,
    body: OverheadMaterialUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    overhead = await db.get(OverheadMaterial, overhead_id)
    if overhead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Overhead material not found"
        )

    payload = body.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(overhead, key, value)

    await db.flush()
    await db.refresh(overhead)
    await db.commit()
    return overhead


@router.delete("/{overhead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_overhead_material(
    overhead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    overhead = await db.get(OverheadMaterial, overhead_id)
    if overhead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Overhead material not found"
        )
    overhead.is_active = False
    await db.commit()


# ---- MAT-2: Overhead receipts (expense events) ----


def _serialize_overhead_receipt(
    receipt: OverheadMaterialReceipt, shop_name: str | None
) -> OverheadMaterialReceiptRead:
    return OverheadMaterialReceiptRead(
        id=receipt.id,
        overhead_material_id=receipt.overhead_material_id,
        shop_id=receipt.shop_id,
        shop_name=shop_name,
        qty=receipt.qty,
        total_cost=receipt.total_cost,
        currency=receipt.currency,
        supplier=receipt.supplier,
        invoice_no=receipt.invoice_no,
        received_at=receipt.received_at,
        notes=receipt.notes,
        user_id=receipt.user_id,
        created_at=receipt.created_at,
    )


@router.post(
    "/{overhead_id}/receipts",
    response_model=OverheadMaterialReceiptRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_overhead_receipt(
    overhead_id: uuid.UUID,
    body: OverheadMaterialReceiptCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    overhead = await db.get(OverheadMaterial, overhead_id)
    if overhead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Overhead material not found"
        )

    shop_name: str | None = None
    if body.shop_id is not None:
        shop = await db.get(Shop, body.shop_id)
        if shop is None or not shop.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Shop {body.shop_id} not found or inactive",
            )
        # USER-ACCESS-1: a manager may only allocate a receipt to a shop they can
        # access (checked after existence so a bad id still returns 422, not 403).
        scope = await get_shop_scope(db, user)
        if not scope.can_access(body.shop_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this shop",
            )
        shop_name = shop.name

    receipt = OverheadMaterialReceipt(
        overhead_material_id=overhead_id,
        shop_id=body.shop_id,
        qty=body.qty,
        total_cost=body.total_cost,
        currency=body.currency,
        supplier=body.supplier,
        invoice_no=body.invoice_no,
        received_at=body.received_at or datetime.now(timezone.utc),
        notes=body.notes,
        user_id=user.id,
    )
    db.add(receipt)
    await db.flush()
    await db.refresh(receipt)
    await db.commit()
    return _serialize_overhead_receipt(receipt, shop_name)


@router.get(
    "/{overhead_id}/receipts",
    response_model=List[OverheadMaterialReceiptRead],
)
async def list_overhead_receipts(
    overhead_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    overhead = await db.get(OverheadMaterial, overhead_id)
    if overhead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Overhead material not found"
        )

    offset = (page - 1) * limit
    stmt = (
        select(OverheadMaterialReceipt, Shop.name)
        .outerjoin(Shop, Shop.id == OverheadMaterialReceipt.shop_id)
        .where(OverheadMaterialReceipt.overhead_material_id == overhead_id)
        .order_by(OverheadMaterialReceipt.received_at.desc())
        .offset(offset)
        .limit(limit)
    )
    # USER-ACCESS-1: a manager sees only receipts for accessible shops, plus the
    # unallocated (shop_id IS NULL) ones. Owner sees all.
    scope = await get_shop_scope(db, user)
    if not scope.is_unrestricted:
        stmt = stmt.where(
            or_(
                OverheadMaterialReceipt.shop_id.is_(None),
                OverheadMaterialReceipt.shop_id.in_(scope.shop_ids),
            )
        )
    result = await db.execute(stmt)
    rows = result.all()
    return [_serialize_overhead_receipt(r, shop_name) for r, shop_name in rows]
