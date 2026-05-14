"""
OrderHub CRM — BOM Service

MAT-3: read + replace recipes; compute theoretical unit cost grouped by
material currency.

The router owns the commit boundary. `replace_bom` runs DELETE-all + bulk
INSERT inside one transaction (no diff-patch — BOM size is small, 3-10 rows
typically; design doc §5.3 + task.md OQ #3).

Inactive-material policy (task.md OQ #4): PUT rejects new BomItems whose
material_id points to a soft-deleted Material. BomItems that were already in
the recipe before the PUT can keep referencing the now-inactive material —
historical recipes stay intact.
"""

import uuid
from decimal import Decimal
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from models.bom import BomItem
from models.material import Material
from schemas.bom import BomCostBreakdown, BomItemCreate, BomItemRead


async def get_bom(
    db: AsyncSession, *, product_id: uuid.UUID
) -> tuple[list[BomItem], bool]:
    """Return BomItems for a product (joined material), and a flag indicating
    whether any line references a soft-deleted Material."""
    stmt = (
        select(BomItem)
        .options(joinedload(BomItem.material))
        .join(Material, BomItem.material_id == Material.id)
        .where(BomItem.product_id == product_id)
        .order_by(Material.name)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    has_inactive = any(not bi.material.is_active for bi in items)
    return items, has_inactive


async def compute_bom_cost(
    db: AsyncSession, *, product_id: uuid.UUID
) -> list[BomCostBreakdown]:
    """SUM(qty_per_unit * material.current_unit_cost) grouped by material.currency.

    For the v1 UAH-only catalog this returns a single row; the schema permits
    multi-currency so MAT-5/FIN-* don't have to revisit the wire format.
    """
    stmt = (
        select(
            Material.currency,
            func.sum(BomItem.qty_per_unit * Material.current_unit_cost),
        )
        .join(Material, BomItem.material_id == Material.id)
        .where(BomItem.product_id == product_id)
        .group_by(Material.currency)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        BomCostBreakdown(
            currency=currency,
            amount=(amount or Decimal("0")).quantize(Decimal("0.01")),
        )
        for currency, amount in rows
    ]


async def replace_bom(
    db: AsyncSession,
    *,
    product_id: uuid.UUID,
    items: Iterable[BomItemCreate],
) -> tuple[list[BomItem], bool]:
    """Transactional DELETE-all + bulk INSERT. Caller commits.

    Validates that every input material_id exists, and rejects any that point
    to an inactive Material UNLESS that material_id was already in the prior
    recipe (grandfathered for historical preservation).
    """
    items = list(items)

    # 1. Read prior recipe so we know which material_ids are grandfathered.
    existing_q = await db.execute(
        select(BomItem.material_id).where(BomItem.product_id == product_id)
    )
    existing_ids = set(existing_q.scalars().all())

    # 2. Validate every input material_id exists; reject inactive unless grandfathered.
    if items:
        input_ids = [item.material_id for item in items]
        materials_q = await db.execute(
            select(Material).where(Material.id.in_(input_ids))
        )
        by_id: dict[uuid.UUID, Material] = {m.id: m for m in materials_q.scalars().all()}
        for item in items:
            mat = by_id.get(item.material_id)
            if mat is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Material {item.material_id} does not exist",
                )
            if not mat.is_active and item.material_id not in existing_ids:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Material '{mat.name}' is discontinued; "
                        "restore it or pick an active replacement"
                    ),
                )

    # 3. Replace-all.
    await db.execute(delete(BomItem).where(BomItem.product_id == product_id))
    for item in items:
        db.add(
            BomItem(
                product_id=product_id,
                material_id=item.material_id,
                qty_per_unit=item.qty_per_unit,
                notes=item.notes,
            )
        )
    await db.flush()

    return await get_bom(db, product_id=product_id)


def project_bom_item(item: BomItem) -> BomItemRead:
    """Hydrate the read schema from a BomItem with its joined Material."""
    mat = item.material
    return BomItemRead(
        id=item.id,
        product_id=item.product_id,
        material_id=item.material_id,
        qty_per_unit=item.qty_per_unit,
        notes=item.notes,
        material_name=mat.name,
        material_unit=mat.unit,
        material_currency=mat.currency,
        material_current_unit_cost=mat.current_unit_cost,
        material_is_active=mat.is_active,
    )
