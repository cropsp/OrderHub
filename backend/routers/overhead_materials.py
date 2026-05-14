"""
OrderHub CRM — Overhead Materials Router (MAT-1)

CRUD for indirect/consumable materials catalog. Soft-delete via `is_active=False`.
No currency/stock fields — overhead expenses live on OverheadMaterialReceipt in MAT-2.
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.material import OverheadMaterial
from models.user import UserRole
from routers.dependencies import require_role
from schemas.material import (
    OverheadMaterialCreate,
    OverheadMaterialRead,
    OverheadMaterialUpdate,
)


router = APIRouter(prefix="/api/overhead-materials", tags=["Overhead Materials"])


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
