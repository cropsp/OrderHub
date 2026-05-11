"""
OrderHub CRM — Packaging Stock Service (PKG-2)

Single transactional helper for every change to packaging stock. INSERTs one
ledger row AND updates the cached counter PackagingBox.stock_quantity in the
same transaction. Does NOT commit — caller controls the transaction boundary
so the movement participates in the same commit as the triggering write
(TTN create / TTN delete / restock endpoint / box creation).
"""

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.packaging import PackagingBox
from models.stock_movement import PackagingStockMovement, StockMovementReason


async def apply_movement(
    db: AsyncSession,
    *,
    box_id: uuid.UUID,
    delta: int,
    reason: StockMovementReason,
    user_id: uuid.UUID,
    order_id: uuid.UUID | None = None,
    note: str | None = None,
) -> list[str]:
    """
    Stage one ledger row and adjust the cached counter on PackagingBox.

    Returns a list of warning strings — empty in the happy path, one entry
    when the post-delta counter has gone negative. Callers forward the
    warnings to the response payload (PKG-2 Q4: backend computes).
    """
    box = await db.get(PackagingBox, box_id)
    if box is None:
        raise HTTPException(status_code=404, detail=f"Packaging box {box_id} not found")

    movement = PackagingStockMovement(
        box_id=box_id,
        order_id=order_id,
        delta=delta,
        reason=reason,
        note=note,
        user_id=user_id,
    )
    db.add(movement)
    box.stock_quantity = box.stock_quantity + delta

    warnings: list[str] = []
    if box.stock_quantity < 0:
        warnings.append(
            f"Stock for «{box.name}» is now {box.stock_quantity}. Time to restock."
        )
    return warnings
