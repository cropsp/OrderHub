"""
OrderHub CRM — Retro-Consumption Backfill Service (WH-5)

A ONE-OFF, human-initiated catch-up: walk orders that already shipped, resolve
the box each one went out in, persist it, and feed the order into the EXISTING
WH-2 consumption machinery so BOM materials and the box are consumed and costed
by exactly the rules a live shipment gets.

WHY THIS EXISTS

WH-2 (packaging + BOM consumed at SHIPPED) went live 2026-08-07 and is
forward-only by construction, so ~7 months of shipped orders carry no movements
and no COGS. Partner settlements have not started, so a retro run cannot rewrite
a base that has already been paid — that is the whole window, and it closes at the
first settlement (runbook Phase 5).

NO NEW COSTING SEMANTICS. This module resolves a box and calls
`order_consumption_service.consume_materials_for_order` unchanged. Every WH-2 rule
applies as-is: an order with no BOM gets its box consumed but keeps a NULL cost
snapshot; FX buckets are all-or-nothing; movements are dated now (harmless —
finance buckets by order dates, not movement dates); counters may go negative
(runbook Phase 6 levels them by ADJUSTMENT afterwards).

TRANSACTIONS — READ THIS BEFORE CHANGING ANYTHING HERE

This service NEVER commits. Nothing on its path does: `consume_materials_for_order`
does not, `material_stock_service.apply_movement` only stages rows and mutates
`stock_quantity` in-session, and `order_service.update_order` only flushes. That
is precisely what makes a dry run exact rather than an estimate — dry-run and
execute run the SAME code over the SAME service, and the only difference is
whether the outer transaction is committed by `get_db` or rolled back. A dry run
therefore reflects real WAC, real FX, real rounding and the real cascade of stock
going negative across orders, because none of it is simulated.

Dry-run safety consequently rests on that invariant plus two rollbacks (here, at
the end, and again in the router). If you ever add a commit to this path you will
silently turn every dry run into a live one.

Per-order SAVEPOINTs (`begin_nested`) do two jobs:
  1. Failure isolation — the routers/orders.py bulk idiom. Without one, an order
     that half-applied before raising would be committed by the batch's final
     commit while being reported as failed.
  2. Undoing the `packaging_id` write when the consumption turns out to be a
     no-op. The runner cannot know in advance whether the idempotency guard will
     fire — only the service can answer that, and it needs `packaging_id` set
     BEFORE it runs in order to find the box. So the write happens first and the
     savepoint is rolled back when the guard reports a skip. That keeps the guard
     as the single source of truth (task rule 4: do not reimplement it) while
     never claiming an order shipped in a box that was never consumed.

Note for very large runs: a transaction accumulating thousands of write
subtransactions overflows PostgreSQL's 64-entry subxid cache, which makes other
backends fall back to pg_subtrans lookups. `limit` + `shop_id` exist so a prod
run can go in tranches; the idempotency guard makes every tranche resumable.
"""

from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from decimal import Decimal

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from models.bom import BomItem
from models.order import Order, OrderItem, OrderStatus
from models.packaging import PackagingBox
from models.product import Product
from models.user import User
from schemas.order import OrderUpdate
from schemas.warehouse import (
    BackfillOutcome,
    BomCoverage,
    BoxConsumptionCount,
    BoxResolution,
    ConsumptionBackfillReport,
    ConsumptionBackfillRow,
    CurrencyCostTotal,
)
from services import fx_service
from services.order_consumption_service import consume_materials_for_order
from services.order_service import update_order

logger = logging.getLogger(__name__)


# Resolutions that mean "the runner decided this, so persist it onto the order".
# ① and ② are already recorded on the order and are never rewritten — ① is the
# operator's own choice.
_PERSISTED_RESOLUTIONS = (
    BoxResolution.PRODUCT_DEFAULT,
    BoxResolution.PRODUCT_DEFAULT_LARGEST,
)


def _box_preference_key(box: PackagingBox) -> tuple:
    """Sort key for "the largest box involved" (task rule 5 ④, OQ5).

    Inner dims are three NOT NULL ints in mm on the geometry row, so the volume is
    exact and null-safe. Ties break on capacity, then on name — ONLY to make the
    choice deterministic and reproducible between the dry run and the execute run
    that follows it.

    `sort_order` is deliberately not a key: it is `default=0 NOT NULL` and the
    whole seeded catalogue sits at 0, so it would decide nothing while looking
    like it did.
    """
    volume = box.inner_length_mm * box.inner_width_mm * box.inner_height_mm
    return (-volume, -box.max_weight_g, box.name or "")


def resolve_box_for_order(
    order: Order,
    *,
    product_defaults: dict[uuid.UUID, uuid.UUID],
    boxes: dict[uuid.UUID, PackagingBox],
) -> tuple[uuid.UUID | None, BoxResolution]:
    """Decide which box this order shipped in. Pure — no I/O, no mutation.

    Strict priority (task rule 5):
      ① order.packaging_id            — the operator said so; never overwritten
      ② order.computed_packaging_box_id — the parcel calculator's suggestion
      ③ exactly one DISTINCT product default across the order's items
      ④ several distinct defaults → the largest by inner volume (one box per
         parcel, design §2.4)
      ⑤ nothing → no packaging consumption; BOM materials still consumed

    A product with no default expresses NO OPINION, not a veto: NULLs are dropped
    before the distinct-count, so a partially-configured order still resolves
    (Sergii, WH-5 plan review). Items with no variant, or a variant with no
    product link, contribute nothing — the same rule the consumption service uses.
    """
    if order.packaging_id is not None:
        return order.packaging_id, BoxResolution.ORDER_PACKAGING
    if order.computed_packaging_box_id is not None:
        return order.computed_packaging_box_id, BoxResolution.COMPUTED_BOX

    candidates: list[uuid.UUID] = []
    for item in order.items:
        variant = item.variant
        if variant is None or variant.product_id is None:
            continue
        box_id = product_defaults.get(variant.product_id)
        if box_id is not None and box_id not in candidates:
            candidates.append(box_id)

    if not candidates:
        return None, BoxResolution.UNRESOLVED
    if len(candidates) == 1:
        return candidates[0], BoxResolution.PRODUCT_DEFAULT

    # Several products, several boxes, one parcel. Take the largest and say so —
    # a box too small is a claim the parcel could not physically have been packed.
    # A candidate missing from the catalogue cannot be sized; it loses to any that
    # can, and only wins if none can.
    known = [boxes[c] for c in candidates if c in boxes]
    if not known:
        return candidates[0], BoxResolution.PRODUCT_DEFAULT_LARGEST
    largest = sorted(known, key=_box_preference_key)[0]
    return largest.id, BoxResolution.PRODUCT_DEFAULT_LARGEST


def _bom_coverage(order: Order, products_with_bom: set[uuid.UUID]) -> BomCoverage:
    """Classify the order's recipe coverage, folding exactly as the consumption
    service does: an item counts as equipped when its variant's product has at
    least one BomItem, and the denominator is EVERY line item, including ones with
    no variant at all.

    Kept in step with `ConsumptionResult.partial_bom_coverage` by
    tests/test_consumption_backfill.py::test_bom_coverage_matches_the_service —
    the consumption service is not modified by this sprint (task rule 9), so a
    parity test is what pins the two readings together.
    """
    items = list(order.items)
    total = len(items)
    equipped = sum(
        1
        for item in items
        if item.variant is not None
        and item.variant.product_id is not None
        and item.variant.product_id in products_with_bom
    )
    if equipped == 0:
        return BomCoverage.NONE
    if equipped < total:
        return BomCoverage.PARTIAL
    return BomCoverage.FULL


def _order_label(order: Order) -> str:
    """How an order is named in the report's diagnostic lists. order_number is
    NULL for Etsy and manual orders, so external_id is the fallback."""
    return order.order_number or order.external_id


async def _load_box_catalogue(db: AsyncSession) -> dict[uuid.UUID, PackagingBox]:
    """Every box, with its paired Material eagerly loaded.

    Two reasons this is one query up front rather than lookups in the loop:
    PackagingBox.stock_quantity / low_stock_threshold / material_is_active are
    properties over `self.material` (lazy="select"), so a box read without it
    raises MissingGreenlet; and putting every box AND material in the identity map
    makes `update_order`'s existence probe and both `db.get()` calls inside
    `consume_materials_for_order` free.

    Archived boxes are included: a historical order may legitimately have shipped
    in a box that has since been archived, and refusing to consume it would make
    the ledger less true, not more.
    """
    result = await db.execute(
        select(PackagingBox).options(joinedload(PackagingBox.material))
    )
    return {box.id: box for box in result.scalars().unique()}


async def _load_product_defaults(db: AsyncSession) -> dict[uuid.UUID, uuid.UUID]:
    result = await db.execute(
        select(Product.id, Product.default_packaging_box_id).where(
            Product.default_packaging_box_id.isnot(None)
        )
    )
    return {product_id: box_id for product_id, box_id in result.all()}


async def _load_products_with_bom(db: AsyncSession) -> set[uuid.UUID]:
    result = await db.execute(select(distinct(BomItem.product_id)))
    return set(result.scalars().all())


async def _load_candidate_orders(
    db: AsyncSession,
    *,
    statuses: list[OrderStatus],
    shop_id: uuid.UUID | None,
    limit: int | None,
) -> list[Order]:
    query = (
        select(Order)
        .where(Order.status.in_(statuses))
        # Deterministic, so a dry run and the execute run that follows it walk the
        # same orders in the same order — which is what makes `limit` a tranche
        # rather than a lottery.
        .order_by(Order.ordered_at, Order.id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.variant),
            joinedload(Order.shop),
        )
    )
    if shop_id is not None:
        query = query.where(Order.shop_id == shop_id)
    if limit is not None:
        query = query.limit(limit)
    result = await db.execute(query)
    return list(result.scalars().unique())


async def run_consumption_backfill(
    db: AsyncSession,
    *,
    user: User,
    statuses: list[OrderStatus],
    dry_run: bool = True,
    limit: int | None = None,
    shop_id: uuid.UUID | None = None,
) -> ConsumptionBackfillReport:
    """Walk already-shipped orders and feed them through the WH-2 machinery.

    `user` is the OWNER who initiated the run: it owns both the audit row on the
    `packaging_id` write and the `user_id` on every stock movement, so the ledger
    names a human rather than a daemon.

    Does NOT commit. Rolls the whole transaction back when `dry_run` — see the
    module docstring for why that is the entire dry-run mechanism.
    """
    # Resolved ONCE, at the transaction boundary, exactly as change_order_status
    # does. resolve() is a pure settings read and never calls NBU.
    fx = await fx_service.resolve(db)

    boxes = await _load_box_catalogue(db)
    product_defaults = await _load_product_defaults(db)
    products_with_bom = await _load_products_with_bom(db)
    orders = await _load_candidate_orders(
        db, statuses=statuses, shop_id=shop_id, limit=limit
    )

    rows: list[ConsumptionBackfillRow] = []
    box_units: "OrderedDict[uuid.UUID, int]" = OrderedDict()
    cost_totals: "OrderedDict[str, list]" = OrderedDict()
    consumed = already = failed = 0

    for order in orders:
        # Everything the report needs is captured BEFORE the savepoint: a rollback
        # expires the instance, and re-reading it afterwards would emit a query per
        # order to recover values we already had.
        box_id, resolution = resolve_box_for_order(
            order, product_defaults=product_defaults, boxes=boxes
        )
        resolved_box = boxes.get(box_id) if box_id is not None else None
        row = ConsumptionBackfillRow(
            order_id=order.id,
            order_number=order.order_number,
            external_id=order.external_id,
            shop_name=order.shop.name if order.shop else "—",
            ordered_at=order.ordered_at,
            status=order.status,
            currency=order.currency,
            resolution=resolution,
            resolved_box_id=box_id,
            resolved_box_name=resolved_box.name if resolved_box is not None else None,
            bom_coverage=_bom_coverage(order, products_with_bom),
            outcome=BackfillOutcome.CONSUMED,
        )
        label = _order_label(order)

        savepoint = await db.begin_nested()
        try:
            if resolution in _PERSISTED_RESOLUTIONS:
                # Through update_order so the mutation lands in order_status_history
                # exactly as a hand edit would ("Fields updated: packaging_id: …"),
                # and so the consumption service needs no change at all to find it.
                await update_order(
                    db, order, OrderUpdate(packaging_id=box_id), user
                )
                row.packaging_id_written = True

            result = await consume_materials_for_order(db, order, user.id, fx=fx)

            if result.idempotent_skip:
                # Nothing was consumed, so nothing may claim to have been packed:
                # undo the packaging_id write together with its audit row.
                await savepoint.rollback()
                row.outcome = BackfillOutcome.ALREADY_CONSUMED
                row.packaging_id_written = False
                already += 1
                rows.append(row)
                continue

            # The service does not write these four; its caller always has, and
            # they move together or not at all (order_service.change_order_status).
            order.computed_production_cost = result.computed_production_cost
            order.cogs_fx_rate = result.fx_rate_used
            order.cogs_basis_amount = result.basis_amount
            order.cogs_basis_currency = result.basis_currency
            await savepoint.commit()
        except Exception as exc:  # noqa: BLE001 — one order must not abort the batch
            await savepoint.rollback()
            logger.error(
                f"[WH-5] Retro consumption failed for order {label} ({order.id}): {exc}",
                exc_info=True,
            )
            row.outcome = BackfillOutcome.FAILED
            row.packaging_id_written = False
            row.error = str(getattr(exc, "detail", None) or exc)
            failed += 1
            rows.append(row)
            continue

        consumed += 1
        row.packaging_consumed = result.packaging_consumed
        row.backfill_production_cost = result.computed_production_cost
        row.warnings = list(result.warnings)
        rows.append(row)

        if result.packaging_consumed and box_id is not None:
            box_units[box_id] = box_units.get(box_id, 0) + 1
        if result.computed_production_cost is not None:
            bucket = cost_totals.setdefault(order.currency, [Decimal("0"), 0])
            bucket[0] += result.computed_production_cost
            bucket[1] += 1

    consumed_rows = [r for r in rows if r.outcome == BackfillOutcome.CONSUMED]
    consumed_labels = {
        r.order_id: (r.order_number or r.external_id) for r in consumed_rows
    }

    report = ConsumptionBackfillReport(
        dry_run=dry_run,
        statuses=statuses,
        shop_id=shop_id,
        limit=limit,
        orders_total=len(orders),
        orders_consumed=consumed,
        orders_already_consumed=already,
        orders_failed=failed,
        boxes_consumed=[
            BoxConsumptionCount(
                box_id=bid,
                box_name=boxes[bid].name if bid in boxes else "—",
                units=units,
            )
            for bid, units in box_units.items()
        ],
        cost_totals=[
            CurrencyCostTotal(
                currency=currency,
                backfill_production_cost_total=total,
                orders=count,
            )
            for currency, (total, count) in cost_totals.items()
        ],
        # Restricted to orders this run consumed: an order the guard skipped was
        # not re-decided here, so listing it would be noise.
        orders_without_bom=[
            consumed_labels[r.order_id]
            for r in consumed_rows
            if r.bom_coverage == BomCoverage.NONE
        ],
        orders_without_box=[
            consumed_labels[r.order_id]
            for r in consumed_rows
            if not r.packaging_consumed
        ],
        orders_ambiguous_default=[
            consumed_labels[r.order_id]
            for r in consumed_rows
            if r.resolution == BoxResolution.PRODUCT_DEFAULT_LARGEST
        ],
        rows=rows,
    )

    logger.info(
        f"[WH-5] Retro consumption {'DRY RUN' if dry_run else 'EXECUTED'}: "
        f"total={report.orders_total} consumed={report.orders_consumed} "
        f"already={report.orders_already_consumed} failed={report.orders_failed} "
        f"boxes={sum(b.units for b in report.boxes_consumed)}"
    )

    if dry_run:
        # The entire dry-run mechanism. Nothing on this path commits, so discarding
        # the transaction discards every movement, cost snapshot, packaging_id and
        # audit row the run just staged. The router repeats this as a second,
        # independent guard.
        await db.rollback()

    return report
