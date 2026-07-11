"""
OrderHub CRM — Material Stock Service (MAT-2)

Single transactional helper for every change to direct-material stock —
weighted-average recompute on receipt, append-only ledger insert on every
movement, and stock_quantity update — all in the caller's transaction.

**Does NOT commit.** Caller controls the transaction boundary so the movement
participates in the same commit as the triggering write (receipt POST, adjust
POST, MAT-4 consumption hook on SHIPPED).

Standalone sibling of services/stock_service.py (PKG-2 packaging helper). NOT
refactored into a shared abstraction — task.md rule #2. If a third use case
emerges later, extract then. YAGNI now.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from models.material import (
    Material,
    MaterialMovement,
    MaterialMovementReason,
    MaterialReceipt,
)


async def apply_movement(
    db: AsyncSession,
    *,
    material_id: uuid.UUID,
    delta: Decimal,
    reason: MaterialMovementReason,
    user_id: uuid.UUID,
    receipt_id: uuid.UUID | None = None,
    order_id: uuid.UUID | None = None,
    unit_cost_at_movement: Decimal | None = None,
    notes: str | None = None,
) -> MaterialMovement:
    """Stage one MaterialMovement and adjust Material.stock_quantity.

    The Python guard mirrors the DB CHECK constraint so violations surface as
    helpful 422s instead of opaque IntegrityErrors at flush time.
    """
    if reason == MaterialMovementReason.CONSUMPTION and unit_cost_at_movement is None:
        raise HTTPException(
            status_code=422,
            detail="unit_cost_at_movement is required for consumption movements",
        )
    if reason != MaterialMovementReason.CONSUMPTION and unit_cost_at_movement is not None:
        raise HTTPException(
            status_code=422,
            detail="unit_cost_at_movement is only allowed on consumption movements",
        )

    material = await db.get(Material, material_id)
    if material is None:
        raise HTTPException(
            status_code=404, detail=f"Material {material_id} not found"
        )

    movement = MaterialMovement(
        material_id=material_id,
        delta=delta,
        reason=reason,
        order_id=order_id,
        receipt_id=receipt_id,
        unit_cost_at_movement=unit_cost_at_movement,
        notes=notes,
        user_id=user_id,
    )
    db.add(movement)
    material.stock_quantity = material.stock_quantity + delta
    return movement


async def apply_receipt(
    db: AsyncSession,
    *,
    material: Material,
    qty: Decimal,
    unit_cost: Decimal,
    currency: str,
    shipping_cost: Decimal | None,
    supplier: str | None,
    invoice_no: str | None,
    received_at: datetime | None,
    notes: str | None,
    is_initial: bool,
    user_id: uuid.UUID,
) -> MaterialReceipt:
    """Compose the full receipt-apply sequence inside the caller's transaction.

    Sequence (no internal commits):
      1. Validate currency match + positive qty.
      2. INSERT MaterialReceipt and flush so receipt.id is materialized.
      3. Compute weighted-average using the OLD stock_quantity.
      4. UPDATE Material.current_unit_cost.
      5. apply_movement(reason=RECEIPT) — stages ledger row AND increments
         Material.stock_quantity (so the +qty happens AFTER step 3, exactly
         as design doc §4.1 prescribes).
    """
    if currency != material.currency:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Receipt currency {currency!r} does not match material currency "
                f"{material.currency!r}"
            ),
        )
    if qty <= 0:
        raise HTTPException(status_code=422, detail="Receipt qty must be > 0")
    if unit_cost < 0:
        raise HTTPException(status_code=422, detail="unit_cost must be >= 0")
    if shipping_cost is not None and shipping_cost < 0:
        raise HTTPException(status_code=422, detail="shipping_cost must be >= 0")

    receipt = MaterialReceipt(
        material_id=material.id,
        qty=qty,
        unit_cost=unit_cost,
        currency=currency,
        shipping_cost=shipping_cost,
        is_initial=is_initial,
        supplier=supplier,
        invoice_no=invoice_no,
        received_at=received_at or datetime.now(timezone.utc),
        notes=notes,
        user_id=user_id,
    )
    db.add(receipt)
    await db.flush()  # materialize receipt.id for the movement FK

    # Weighted-average recompute — uses OLD stock_quantity (still untouched).
    ship = shipping_cost if shipping_cost is not None else Decimal("0")
    effective_unit_cost = (qty * unit_cost + ship) / qty
    # Negative stock is a permitted state (MAT-4). When stock <= 0 the weighted
    # average is undefined (stock == -qty divides by zero; -qty < stock < 0 yields a
    # nonsensical/negative cost), so treat the receipt as re-baselining the unit cost.
    if material.stock_quantity <= 0:
        new_avg = effective_unit_cost
    else:
        new_avg = (
            (material.stock_quantity * material.current_unit_cost)
            + (qty * effective_unit_cost)
        ) / (material.stock_quantity + qty)
    material.current_unit_cost = new_avg

    # Ledger row + stock_quantity increment (apply_movement does the += qty).
    await apply_movement(
        db,
        material_id=material.id,
        delta=qty,
        reason=MaterialMovementReason.RECEIPT,
        user_id=user_id,
        receipt_id=receipt.id,
        notes=None,
    )
    return receipt
