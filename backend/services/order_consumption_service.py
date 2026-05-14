"""
OrderHub CRM — Order Consumption Service (MAT-4)

Material decrements + Order.computed_production_cost snapshot on Order → SHIPPED.

Called by services.order_service.change_order_status() immediately after the
OrderStatusHistory row is staged and flush()ed, before the caller's commit.
The single entry point — consume_materials_for_order — is responsible for:

  1. Idempotency guard: SELECT 1 FROM material_movements WHERE order_id = order.id
     AND reason = 'consumption' LIMIT 1. If a row exists → no-op (re-SHIPPED).
  2. Iterating OrderItems, walking variant → product → BomItem rows, computing
     actual_consumed = qty_per_unit * order_item.quantity * (1 + waste_percent/100).
  3. Calling material_stock_service.apply_movement for each BomItem (which both
     stages the MaterialMovement row AND mutates Material.stock_quantity in
     the caller's session — no commit here).
  4. Summing per-line cost contributions (un-rounded, rounded ONCE at the end).
  5. Validating Material.currency == Order.currency. On mismatch: skip the cost
     rollup (return computed_production_cost=None + warning), but consumption
     movements still fire (stock stays honest — design §9 #1).

Transactional integrity: does NOT commit. The caller (routers/orders.py or
routers/shipping.py via change_order_status) owns the commit. If anything in
the loop raises, the whole transition rolls back.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from models.bom import BomItem
from models.material import Material, MaterialMovement, MaterialMovementReason
from models.order import Order, OrderItem
from services import material_stock_service


@dataclass
class ConsumptionResult:
    computed_production_cost: Decimal | None = None
    warnings: list[str] = field(default_factory=list)
    partial_bom_coverage: bool = False
    negative_stock_materials: list[str] = field(default_factory=list)
    idempotent_skip: bool = False


async def consume_materials_for_order(
    db: AsyncSession, order: Order, user_id: uuid.UUID
) -> ConsumptionResult:
    """Single entry point for MAT-4 consumption hook.

    Does NOT commit. Mutates Material.stock_quantity in-session via
    material_stock_service.apply_movement; caller commits or rolls back.
    """
    # 1. Idempotency — never double-consume on SHIPPED → IN_PROGRESS → SHIPPED.
    existing = await db.execute(
        select(MaterialMovement.id)
        .where(
            MaterialMovement.order_id == order.id,
            MaterialMovement.reason == MaterialMovementReason.CONSUMPTION,
        )
        .limit(1)
    )
    if existing.scalar() is not None:
        return ConsumptionResult(idempotent_skip=True)

    # 2. Defensive currency check. Order.currency has a DB default of "USD" so
    #    this is mostly belt-and-suspenders against legacy data.
    order_currency = (order.currency or "").strip()
    if not order_currency:
        return ConsumptionResult(
            warnings=["⚠ Order has no currency set; cost calculation skipped."]
        )

    # 3. Load items with their variants (variant.product_id drives BOM lookup).
    items_q = await db.execute(
        select(OrderItem)
        .where(OrderItem.order_id == order.id)
        .options(selectinload(OrderItem.variant))
    )
    items = list(items_q.scalars())
    if not items:
        return ConsumptionResult()

    total_cost = Decimal("0")
    bom_equipped = 0
    currency_mismatch_names: list[str] = []
    negative_stock: list[str] = []

    for item in items:
        if item.variant is None or item.variant.product_id is None:
            # Manual / free-text order item or variant without a product link.
            continue

        bom_q = await db.execute(
            select(BomItem).where(BomItem.product_id == item.variant.product_id)
        )
        # BomItem.material is lazy="joined" (models/bom.py), so the relationship
        # is materialised on attribute access without a second query.
        bom_items = list(bom_q.scalars())
        if not bom_items:
            continue

        bom_equipped += 1

        for bom in bom_items:
            material: Material = bom.material

            if material.currency != order_currency:
                if material.name not in currency_mismatch_names:
                    currency_mismatch_names.append(material.name)

            waste_factor = Decimal("1") + (
                material.waste_percent / Decimal("100")
            )
            actual = (
                bom.qty_per_unit * Decimal(item.quantity) * waste_factor
            )
            # stock_quantity is Decimal(12,2) so the ledger delta rounds to 2dp.
            actual_rounded = actual.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            unit_cost_snapshot = material.current_unit_cost

            await material_stock_service.apply_movement(
                db,
                material_id=material.id,
                delta=-actual_rounded,
                reason=MaterialMovementReason.CONSUMPTION,
                user_id=user_id,
                order_id=order.id,
                unit_cost_at_movement=unit_cost_snapshot,
            )
            # apply_movement already did `material.stock_quantity += delta`.
            if (
                material.stock_quantity < 0
                and material.name not in negative_stock
            ):
                negative_stock.append(material.name)

            # Cost contribution uses the un-rounded delta; round once at SUM.
            total_cost += actual * unit_cost_snapshot

    warnings: list[str] = []
    total_items = len(items)

    if currency_mismatch_names:
        warnings.append(
            f"⚠ Cannot compute production cost: "
            f"{len(currency_mismatch_names)} of {total_items} line-item "
            f"materials are priced in a different currency than the order "
            f"({order_currency}). Multi-currency cost conversion is not "
            f"supported in v1."
        )
        computed_cost: Decimal | None = None
    elif bom_equipped == 0:
        computed_cost = None
    else:
        computed_cost = total_cost.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    partial = 0 < bom_equipped < total_items
    if partial:
        warnings.append(
            f"ⓘ Computed cost reflects {bom_equipped} of {total_items} "
            f"line items; {total_items - bom_equipped} products have no "
            f"BOM defined."
        )

    for name in negative_stock:
        warnings.append(
            f"⚠ Stock for «{name}» went negative. Time to restock."
        )

    return ConsumptionResult(
        computed_production_cost=computed_cost,
        warnings=warnings,
        partial_bom_coverage=partial,
        negative_stock_materials=negative_stock,
    )
