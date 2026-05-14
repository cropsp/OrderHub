"""
OrderHub CRM — Materials Router (MAT-1)

CRUD for direct materials catalog. Soft-delete via `is_active=False` (returns 204).
Currency is locked at creation; `MaterialUpdate` schema omits the field so PATCH
silently ignores any client-supplied currency (matches Shop/Packaging convention).
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.material import Material
from models.user import UserRole
from routers.dependencies import require_role
from schemas.material import MaterialCreate, MaterialRead, MaterialUpdate


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
