"""
OrderHub CRM — Etsy statement import service (STATEMENT-IMPORT)

Turns a parsed Etsy payment-account statement into:
  - exact per-order `Order.platform_fee` (Fee + fee-VAT rows, SIGNED), and
  - two monthly `OverheadMaterialReceipt` rows per shop — advertising, and
    listing/account fees.

The accounting split (decided 2026-08-04, calibrated against six real monthly
statements covering 210 orders):

  Fee + fee-VAT   -> order.platform_fee     16.05% of base   per-sale cost
  ads + ads-VAT   -> "Etsy Ads" overhead    15.75% of base   discretionary spend
  listing + its VAT -> "Etsy listing & account fees" overhead   0.73% of base
                                            ------
                                            32.53% all-in

VAT follows the line it taxes rather than all landing on the order: 180 of the
VAT rows are VAT on daily Etsy Ads and carry NO order number, so booking them to
a per-order bucket would strand $152.95 that no order can ever receive.

Listing and auto-renew fees carry no order number either — hence their own
overhead row. Without it $58.16 of real cost has nowhere to go and the import
cannot reconcile against the statement it came from.

IDEMPOTENCY — replace by period. An import DELETEs every line for
`(shop_id, period_month)` and re-inserts the file whole, then recomputes the
affected orders' fees from ALL accumulated periods. This is what makes
re-uploading a file a no-op, keeps legitimately duplicated rows (nothing
de-duplicates), and handles a re-issued statement correctly — rows that vanished
from the re-issue are actually gone, which upserting could never achieve.

DRY RUN — the same code path, rolled back. `dry_run=True` (the default, as on
SHOP-FEE-1's backfill) runs the import whole and then ROLLS BACK before
returning, so the report is identical to the one a real import would produce,
field for field, except `dry_run` itself. It is identical by construction rather
than by care: every figure in the report is a SQL aggregate over the lines this
import just inserted, so a "compute without writing" rehearsal would be a second
derivation of the same money — and a rehearsal that can disagree with the
performance is worse than none. The price is that a dry run really does write
inside its transaction and take the same locks for its duration; it is not a
read-only operation. The rollback lives here, not in the caller, so the
guarantee sits beside the writes it undoes.

This service writes overhead receipts through the ORM rather than the overhead
REST router on purpose: that router is append-only (no PATCH/DELETE exists, by
design) and its create schema forbids a negative `total_cost`, but a
credit-heavy month is a real, honest negative. Only rows this importer owns —
those carrying its `source_ref` marker — are ever updated.
"""

import calendar
import logging
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.etsy_statement_line import EtsyStatementLine
from models.material import OverheadMaterial, OverheadMaterialReceipt
from models.order import Order
from models.shop import Shop
from schemas.etsy_statement import (
    StatementImportReport,
    StatementFeeOverride,
    StatementUnmatchedOrder,
)
from services.etsy_statement_parser import (
    ACCOUNT_FEE_OVERHEAD_BUCKETS,
    ADS_OVERHEAD_BUCKETS,
    BUCKET_DEPOSIT,
    BUCKET_REFUND,
    BUCKET_SALE,
    BUCKET_TAX,
    PLATFORM_FEE_BUCKETS,
    ParsedStatement,
    StatementParseError,
    parse_statement_csv,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")

#: Overhead materials this importer books into, created on first use. Matched by
#: exact name (the table has no unique constraint on `name`, so a fuzzy lookup
#: could silently attach to an operator's similarly-named row).
ADS_OVERHEAD_MATERIAL = "Etsy Ads"
ACCOUNT_FEE_OVERHEAD_MATERIAL = "Etsy listing & account fees"
OVERHEAD_UNIT = "month"

SOURCE_REF_PREFIX = "etsy-stmt"


def _source_ref(period_month: date, scope: str) -> str:
    return f"{SOURCE_REF_PREFIX}:{period_month:%Y-%m}:{scope}"


def _period_end(period_month: date) -> datetime:
    """Last calendar day of the period, midnight UTC.

    Finance buckets overhead by `cast(received_at, Date)`, so any instant inside
    the month works; month-end is the least surprising for a statement charge and
    is deterministic regardless of when the import runs.
    """
    last_day = calendar.monthrange(period_month.year, period_month.month)[1]
    return datetime.combine(
        period_month.replace(day=last_day), time.min, tzinfo=timezone.utc
    )


async def import_statement(
    db: AsyncSession,
    shop: Shop,
    content: bytes,
    filename: str,
    user_id: uuid.UUID,
    *,
    dry_run: bool = True,
) -> StatementImportReport:
    """Import one monthly statement for `shop`. Caller commits.

    Raises `StatementParseError` (surfaced as 400) if any row is unrecognised —
    nothing is written when that happens.

    `dry_run=True` (the default, mirroring SHOP-FEE-1) produces the identical
    report and then rolls the transaction back — see "DRY RUN" in the module
    docstring. The caller must not commit afterwards.
    """
    parsed = parse_statement_csv(content, filename)
    period = parsed.period_month

    order_by_external = await _resolve_orders(db, shop, parsed)

    previous = await _existing_period_state(db, shop, period)
    affected_order_ids = set(previous["order_ids"])

    await db.execute(
        delete(EtsyStatementLine).where(
            EtsyStatementLine.shop_id == shop.id,
            EtsyStatementLine.period_month == period,
        )
    )

    matched_ids: set[str] = set()
    unmatched_totals: dict[str, Decimal] = {}
    for line in parsed.lines:
        order = (
            order_by_external.get(line.order_external_id)
            if line.order_external_id
            else None
        )
        if line.order_external_id:
            if order is not None:
                matched_ids.add(line.order_external_id)
                if line.bucket in PLATFORM_FEE_BUCKETS:
                    affected_order_ids.add(order.id)
            elif line.bucket in PLATFORM_FEE_BUCKETS:
                # Rule 7: never create an order, never guess a match. Count it,
                # sum what it would have cost, and report it.
                unmatched_totals[line.order_external_id] = (
                    unmatched_totals.get(line.order_external_id, ZERO)
                    - line.net_signed
                )
            else:
                unmatched_totals.setdefault(line.order_external_id, ZERO)

        db.add(
            EtsyStatementLine(
                shop_id=shop.id,
                period_month=period,
                row_index=line.row_index,
                entry_date=line.entry_date,
                entry_type=line.entry_type,
                title=line.title,
                info=line.info,
                currency=line.currency,
                amount_signed=line.amount_signed,
                fees_taxes_signed=line.fees_taxes_signed,
                net_signed=line.net_signed,
                bucket=line.bucket,
                order_external_id=line.order_external_id,
                listing_external_id=line.listing_external_id,
                order_id=order.id if order is not None else None,
                source_filename=filename[:255] if filename else None,
                file_sha256=parsed.file_sha256,
                imported_by_user_id=user_id,
            )
        )

    await db.flush()

    overrides, credit_only = await _recompute_platform_fees(
        db, shop, affected_order_ids, previous["fees"]
    )

    ads_total = await _book_overhead(
        db,
        shop,
        period,
        buckets=ADS_OVERHEAD_BUCKETS,
        material_name=ADS_OVERHEAD_MATERIAL,
        scope="ads",
        user_id=user_id,
    )
    account_total = await _book_overhead(
        db,
        shop,
        period,
        buckets=ACCOUNT_FEE_OVERHEAD_BUCKETS,
        material_name=ACCOUNT_FEE_OVERHEAD_MATERIAL,
        scope="account-fees",
        user_id=user_id,
    )

    await db.flush()

    totals = _bucket_totals(parsed)
    logger.info(
        "[STATEMENT-IMPORT] shop=%s period=%s dry_run=%s lines=%d (replaced %d) "
        "matched=%d unmatched=%d ads=%s account=%s",
        shop.id,
        period,
        dry_run,
        len(parsed.lines),
        previous["line_count"],
        len(matched_ids),
        len(unmatched_totals),
        ads_total,
        account_total,
    )

    report = StatementImportReport(
        dry_run=dry_run,
        period=f"{period:%Y-%m}",
        source_filename=filename,
        file_sha256=parsed.file_sha256,
        identical_file=(
            previous["file_sha256"] is not None
            and previous["file_sha256"] == parsed.file_sha256
        ),
        lines_imported=len(parsed.lines),
        lines_replaced=previous["line_count"],
        orders_matched=len(matched_ids),
        orders_unmatched=len(unmatched_totals),
        unmatched_orders=[
            StatementUnmatchedOrder(order_external_id=k, platform_fee_amount=v)
            for k, v in sorted(unmatched_totals.items())
        ],
        fee_overrides=overrides,
        credit_only_orders=credit_only,
        ads_overhead_amount=ads_total,
        account_fee_overhead_amount=account_total,
        sales_count=totals["sales_count"],
        statement_base_amount=totals["base"],
        refunds_count=totals["refunds_count"],
        refunds_amount=totals["refunds"],
        deposits_count=totals["deposits_count"],
        deposits_amount=totals["deposits"],
    )

    if dry_run:
        # The rehearsal is over. Everything above ran for real inside this
        # transaction; abandoning it is what makes the report trustworthy AND
        # the database untouched. The report holds only plain values, so it
        # survives the rollback intact.
        await db.rollback()

    return report


async def _resolve_orders(
    db: AsyncSession, shop: Shop, parsed: ParsedStatement
) -> dict[str, Order]:
    """Map Etsy order number -> local Order, scoped to this shop.

    Scoping to `shop_id` is deliberate: `Order` is unique on
    `(external_id, shop_id)`, and cross-shop uniqueness of an Etsy order number
    is never assumed — the operator picks the shop at upload time.
    """
    externals = {
        line.order_external_id for line in parsed.lines if line.order_external_id
    }
    if not externals:
        return {}
    rows = await db.execute(
        select(Order).where(
            Order.shop_id == shop.id, Order.external_id.in_(externals)
        )
    )
    return {o.external_id: o for o in rows.scalars()}


async def _existing_period_state(
    db: AsyncSession, shop: Shop, period: date
) -> dict:
    """What is already stored for this shop+period, captured BEFORE the delete.

    Orders that had fee lines in the outgoing period must be recomputed even if
    the incoming file no longer mentions them — otherwise a corrected statement
    would leave a stale fee behind.
    """
    rows = await db.execute(
        select(EtsyStatementLine).where(
            EtsyStatementLine.shop_id == shop.id,
            EtsyStatementLine.period_month == period,
        )
    )
    lines = list(rows.scalars())
    order_ids = {
        line.order_id
        for line in lines
        if line.order_id is not None and line.bucket in PLATFORM_FEE_BUCKETS
    }
    fees: dict[uuid.UUID, Decimal | None] = {}
    if order_ids:
        existing = await db.execute(
            select(Order.id, Order.platform_fee).where(Order.id.in_(order_ids))
        )
        fees = {row[0]: row[1] for row in existing}
    return {
        "line_count": len(lines),
        "order_ids": order_ids,
        "fees": fees,
        "file_sha256": lines[0].file_sha256 if lines else None,
    }


async def _recompute_platform_fees(
    db: AsyncSession,
    shop: Shop,
    affected_order_ids: set[uuid.UUID],
    previous_fees: dict[uuid.UUID, Decimal | None],
) -> tuple[list[StatementFeeOverride], list[StatementUnmatchedOrder]]:
    """Recompute `platform_fee` for every affected order, across ALL periods.

    The fee is an aggregate over stored lines, never a blind write (rule 1), so
    an overlapping later statement that credits an earlier order updates that
    order by exactly the credit.

    The statement wins over a hand-entered value (rule 6) — the opposite of
    SHOP-FEE-1's flat-rate path, where a manual fee is never overwritten. That is
    why this function exists separately from `order_service.compute_platform_fee`
    and never calls it: the two policies must stay greppably distinct.
    """
    if not affected_order_ids:
        return [], []

    sums = await db.execute(
        select(
            EtsyStatementLine.order_id,
            func.sum(EtsyStatementLine.net_signed),
        )
        .where(
            EtsyStatementLine.shop_id == shop.id,
            EtsyStatementLine.order_id.in_(affected_order_ids),
            EtsyStatementLine.bucket.in_(PLATFORM_FEE_BUCKETS),
        )
        .group_by(EtsyStatementLine.order_id)
    )
    derived = {row[0]: (-row[1]).quantize(ZERO) for row in sums}

    # Orders whose fee went negative: Etsy refunded fees that were charged in a
    # statement period we have not imported. Reported so the operator can decide
    # to load the earlier month rather than silently carry a negative cost.
    sale_rows = await db.execute(
        select(EtsyStatementLine.order_id)
        .where(
            EtsyStatementLine.shop_id == shop.id,
            EtsyStatementLine.order_id.in_(affected_order_ids),
            EtsyStatementLine.bucket == BUCKET_SALE,
        )
        .distinct()
    )
    have_sale = {row[0] for row in sale_rows}

    orders = await db.execute(
        select(Order).where(Order.id.in_(affected_order_ids))
    )
    overrides: list[StatementFeeOverride] = []
    credit_only: list[StatementUnmatchedOrder] = []

    for order in orders.scalars():
        # No lines left anywhere -> NULL, not 0.00. NULL means "not priced" and
        # keeps the order eligible for other pricing paths; 0.00 asserts Etsy
        # charged nothing, which would be a different and untrue claim.
        new_fee = derived.get(order.id)
        old_fee = previous_fees.get(order.id, order.platform_fee)

        if old_fee is not None and new_fee is not None and Decimal(old_fee) != new_fee:
            overrides.append(
                StatementFeeOverride(
                    order_external_id=order.external_id,
                    previous_platform_fee=Decimal(old_fee),
                    statement_platform_fee=new_fee,
                )
            )

        order.platform_fee = new_fee

        if new_fee is not None and new_fee < 0 and order.id not in have_sale:
            credit_only.append(
                StatementUnmatchedOrder(
                    order_external_id=order.external_id,
                    platform_fee_amount=new_fee,
                )
            )

    return overrides, credit_only


async def _book_overhead(
    db: AsyncSession,
    shop: Shop,
    period: date,
    *,
    buckets: frozenset[str],
    material_name: str,
    scope: str,
    user_id: uuid.UUID,
) -> Decimal:
    """Upsert ONE overhead receipt per shop per month for `buckets`.

    Keyed on `source_ref`, so a re-import updates this row rather than appending
    a second one. If the period no longer contributes any such line, the row is
    removed — the period is replaced, not merged.
    """
    total_row = await db.execute(
        select(
            func.coalesce(func.sum(EtsyStatementLine.net_signed), 0),
            func.count(),
        ).where(
            EtsyStatementLine.shop_id == shop.id,
            EtsyStatementLine.period_month == period,
            EtsyStatementLine.bucket.in_(buckets),
        )
    )
    net_sum, line_count = total_row.one()
    amount = (-Decimal(net_sum)).quantize(ZERO)

    ref = _source_ref(period, scope)
    existing = await db.execute(
        select(OverheadMaterialReceipt).where(
            OverheadMaterialReceipt.shop_id == shop.id,
            OverheadMaterialReceipt.source_ref == ref,
        )
    )
    receipt = existing.scalar_one_or_none()

    if line_count == 0:
        if receipt is not None:
            await db.delete(receipt)
        return ZERO

    material = await _get_or_create_overhead_material(db, material_name)
    notes = (
        f"Auto-imported from the Etsy payment statement for {period:%Y-%m} "
        "(STATEMENT-IMPORT). Re-importing that month overwrites this row."
    )

    if receipt is None:
        db.add(
            OverheadMaterialReceipt(
                overhead_material_id=material.id,
                shop_id=shop.id,
                qty=None,
                total_cost=amount,
                currency="USD",
                supplier="Etsy",
                received_at=_period_end(period),
                notes=notes,
                source_ref=ref,
                user_id=user_id,
            )
        )
    else:
        receipt.overhead_material_id = material.id
        receipt.total_cost = amount
        receipt.currency = "USD"
        receipt.received_at = _period_end(period)
        receipt.notes = notes
        receipt.user_id = user_id

    return amount


async def _get_or_create_overhead_material(
    db: AsyncSession, name: str
) -> OverheadMaterial:
    found = await db.execute(
        select(OverheadMaterial).where(OverheadMaterial.name == name).limit(1)
    )
    material = found.scalar_one_or_none()
    if material is not None:
        return material
    material = OverheadMaterial(name=name, unit=OVERHEAD_UNIT, is_active=True)
    db.add(material)
    await db.flush()
    return material


def _bucket_totals(parsed: ParsedStatement) -> dict:
    """Cross-check figures computed straight off the parsed file."""
    sales = [l for l in parsed.lines if l.bucket == BUCKET_SALE]
    taxes = [l for l in parsed.lines if l.bucket == BUCKET_TAX]
    refunds = [l for l in parsed.lines if l.bucket == BUCKET_REFUND]
    deposits = [l for l in parsed.lines if l.bucket == BUCKET_DEPOSIT]
    base = sum((l.amount_signed or ZERO) for l in sales) + sum(
        l.net_signed for l in taxes
    )
    return {
        "sales_count": len(sales),
        # Base = what Etsy charges fees on = Sale - buyer sales tax.
        "base": Decimal(base).quantize(ZERO),
        "refunds_count": len(refunds),
        "refunds": Decimal(
            sum((l.amount_signed or ZERO) for l in refunds)
        ).quantize(ZERO),
        "deposits_count": len(deposits),
        "deposits": Decimal(
            sum((l.amount_signed or ZERO) for l in deposits)
        ).quantize(ZERO),
    }


__all__ = ["import_statement", "StatementParseError"]
