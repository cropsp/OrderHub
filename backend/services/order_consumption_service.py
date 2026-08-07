"""
OrderHub CRM — Order Consumption Service (MAT-4)

Material decrements + Order.computed_production_cost snapshot on Order → SHIPPED.

Called by services.order_service.change_order_status() immediately after the
OrderStatusHistory row is staged and flush()ed, before the caller's commit.
The single entry point — consume_materials_for_order — is responsible for:

  1. Idempotency guard: SELECT 1 FROM material_movements WHERE order_id = order.id
     AND reason = 'consumption' LIMIT 1, OR an already-booked
     order.computed_production_cost. If either holds → no-op (re-SHIPPED).

     The second probe is WH-1's. A recipe made entirely of is_stock_tracked=false
     lines writes NO movement rows, so the ledger probe alone would stop firing for
     such an order and a SHIPPED → IN_PROGRESS → SHIPPED cycle would silently
     re-price a frozen snapshot at today's WAC and today's FX rate — exactly what
     DESIGN §4.1 ("snapshots are immutable") forbids. order_service.py is the only
     writer of computed_production_cost, so a non-NULL value means "already priced".
     An order that has neither (first ship, or a ship whose cost was skipped because
     no FX rate was configured) still runs — for the latter that is the recovery
     path, and there is no snapshot to protect.
  2. Iterating OrderItems, walking variant → product → BomItem rows, computing
     actual_consumed = qty_per_unit * order_item.quantity * (1 + waste_percent/100).
  3. Calling material_stock_service.apply_movement for each BomItem (which both
     stages the MaterialMovement row AND mutates Material.stock_quantity in
     the caller's session — no commit here) — UNLESS the material is
     is_stock_tracked=false, in which case the line contributes its cost exactly as
     any other but moves no stock and writes no ledger row (WH-1, closes
     SVC-MATERIAL-NONSTOCK for service positions like cutting and sewing).
  4. Accumulating per-line cost contributions into PER-CURRENCY buckets
     (un-rounded), converting each bucket into the order currency, and rounding
     ONCE at the end.
  5. Converting Material.currency -> Order.currency via the FxRates passed in by
     the caller (FX-CONVERSION). Same-currency needs no rate. If ANY bucket
     cannot be converted, the whole cost rollup is skipped (return
     computed_production_cost=None + warning) but consumption movements still
     fire (stock stays honest — design §9 #1).

     All-or-nothing is deliberate: summing only the convertible buckets would
     book a too-small COGS, which inflates net profit in finance_service and
     over-pays partner payouts, silently. A missing number is recoverable; a
     plausible wrong one is not.

The FxRates value object is resolved by the CALLER (order_service) and passed in,
not read from the DB here. That keeps the settings lookup out of the consumption
fold, lets the parity test drive this service and bom_service with one identical
rate, and means this path issues no new queries.

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
from services.fx_service import FxRates, normalize_currency


@dataclass
class ConsumptionResult:
    computed_production_cost: Decimal | None = None
    warnings: list[str] = field(default_factory=list)
    partial_bom_coverage: bool = False
    negative_stock_materials: list[str] = field(default_factory=list)
    idempotent_skip: bool = False
    # FX-CONVERSION provenance, mirrored onto the Order by the caller. All None
    # when nothing was booked or no conversion was needed — see models/order.py
    # for the NULL decode rules.
    fx_rate_used: Decimal | None = None
    basis_amount: Decimal | None = None
    basis_currency: str | None = None


async def consume_materials_for_order(
    db: AsyncSession,
    order: Order,
    user_id: uuid.UUID,
    *,
    fx: FxRates | None = None,
) -> ConsumptionResult:
    """Single entry point for MAT-4 consumption hook.

    `fx` is the resolved rate for this transition, supplied by the caller. It
    defaults to an unavailable rate so a caller that has not been updated
    degrades to the pre-FX behaviour (no cross-currency cost) rather than
    silently booking at some other rate.

    Does NOT commit. Mutates Material.stock_quantity in-session via
    material_stock_service.apply_movement; caller commits or rolls back.
    """
    fx = fx or FxRates.unavailable()
    # 1. Idempotency — never double-consume on SHIPPED → IN_PROGRESS → SHIPPED.
    existing = await db.execute(
        select(MaterialMovement.id)
        .where(
            MaterialMovement.order_id == order.id,
            MaterialMovement.reason == MaterialMovementReason.CONSUMPTION,
        )
        .limit(1)
    )
    if existing.scalar() is not None or order.computed_production_cost is not None:
        return ConsumptionResult(idempotent_skip=True)

    # 2. Defensive currency check. Order.currency defaults to "USD" so this is
    #    mostly belt-and-suspenders against legacy data. Normalised because it
    #    is now an FX dispatch key, not just something to compare for equality.
    order_currency = normalize_currency(order.currency)
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

    # Per-material-currency buckets, accumulated UN-ROUNDED. Before FX this was a
    # single running total that summed across currencies blindly — harmless only
    # because a mismatch discarded the result. Now that mismatched currencies can
    # actually be booked, the buckets have to stay separate until conversion.
    totals_by_currency: dict[str, Decimal] = {}
    bom_equipped = 0
    unconvertible_currencies: list[str] = []
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
            material_currency = normalize_currency(material.currency)

            if not fx.can_convert(frm=material_currency, to=order_currency):
                if material_currency not in unconvertible_currencies:
                    unconvertible_currencies.append(material_currency)

            waste_factor = Decimal("1") + (
                material.waste_percent / Decimal("100")
            )
            actual = (
                bom.qty_per_unit * Decimal(item.quantity) * waste_factor
            )
            unit_cost_snapshot = material.current_unit_cost

            # WH-1: `is not False`, not plain truthiness. The column is NOT NULL, so
            # anything loaded from the DB is a real bool; a Material built in memory
            # reads None because column defaults apply at INSERT. Skipping stock must
            # be an explicit opt-in, never the side effect of an unset attribute.
            if material.is_stock_tracked is not False:
                # stock_quantity is Decimal(12,2) so the ledger delta rounds to 2dp.
                actual_rounded = actual.quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
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

            # Cost contribution uses the un-rounded delta; round once at the end.
            totals_by_currency[material_currency] = (
                totals_by_currency.get(material_currency, Decimal("0"))
                + actual * unit_cost_snapshot
            )

    warnings: list[str] = []
    total_items = len(items)
    fx_rate_used: Decimal | None = None
    basis_amount: Decimal | None = None
    basis_currency: str | None = None

    if unconvertible_currencies:
        # All-or-nothing. Booking just the convertible buckets would under-state
        # COGS and over-state profit, silently and permanently (forward-only).
        #
        # Warnings name currencies and counts but NEVER amounts or rates: this
        # list is returned by routers/shipping.py as a raw dict with no
        # response_model, so it is invisible to censor_order_financials and to
        # the money-field guard. Keep it free of money.
        warnings.append(
            f"⚠ Cannot compute production cost: this order uses materials priced "
            f"in {', '.join(sorted(unconvertible_currencies))}, and no exchange "
            f"rate to {order_currency} is configured. Set one in "
            f"Settings › Exchange Rate. Stock was still consumed."
        )
        computed_cost: Decimal | None = None
    elif bom_equipped == 0:
        computed_cost = None
    else:
        # Convert each bucket un-rounded, sum, and quantize exactly ONCE. Rounding
        # per bucket would diverge from bom_service's preview, which folds the
        # same way (guarded by test_bom_waste_parity).
        converted_total = Decimal("0")
        for currency, amount in totals_by_currency.items():
            converted_total += fx.convert(amount, frm=currency, to=order_currency)
            rate = fx.rate_for(frm=currency, to=order_currency)
            if rate is not None:
                fx_rate_used = rate

        computed_cost = converted_total.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # The basis is only meaningful when one material currency is in play — a
        # single figure cannot describe a mixed-currency recipe. Always populated
        # in practice today (every material is UAH).
        if len(totals_by_currency) == 1:
            basis_currency, raw_basis = next(iter(totals_by_currency.items()))
            basis_amount = raw_basis.quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
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
        fx_rate_used=fx_rate_used,
        basis_amount=basis_amount,
        basis_currency=basis_currency,
    )
