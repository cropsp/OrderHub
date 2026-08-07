"""
OrderHub CRM — Finance Service (FIN-1)

Computes per-shop financial overview: KPI aggregates (revenue, COGS,
fees, net profit, pipeline value, order count, AOV), a day-or-month
time series, and the data-quality diagnostic (orders missing cost).

Per the FIN-1 plan:
  - Status filter for revenue/cost/fee aggregates: [COMPLETED, SHIPPED]
  - Date expression: COALESCE(shipped_at, ordered_at) — matches the
    DASH-REVENUE-DATE fix in dashboard.py.
  - Currency: per-currency breakdown, no conversion.
  - change_percent is computed over the primary currency (largest
    current amount); None when previous is 0 or no data.
  - Granularity: day if period <= 90d, else month.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.etsy_statement_line import EtsyStatementLine
from models.material import OverheadMaterialReceipt
from models.order import Order, OrderItem, OrderRefund, OrderStatus
from models.shop import Shop, ShopPlatform
from schemas.finance import (
    CurrencyAmount,
    DiagnosticInfo,
    KpiCard,
    OrderCountCard,
    ShopFinanceResponse,
    TimeSeriesPoint,
)

REVENUE_STATUSES = [OrderStatus.SHIPPED, OrderStatus.COMPLETED]
PIPELINE_EXCLUDED_STATUSES = [
    OrderStatus.SHIPPED,
    OrderStatus.COMPLETED,
    OrderStatus.CANCELLED,
]


def _previous_period(start: date, end: date) -> tuple[date, date]:
    """Same-length window immediately preceding [start, end] (both inclusive)."""
    length_days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length_days - 1)
    return prev_start, prev_end


def _primary_currency(amounts: list[CurrencyAmount]) -> str | None:
    if not amounts:
        return None
    return max(amounts, key=lambda a: a.amount).currency


def _change_percent(
    current: list[CurrencyAmount], previous: list[CurrencyAmount]
) -> float | None:
    """Percent change over the primary (largest-current) currency. None on divide-by-zero."""
    primary = _primary_currency(current)
    if primary is None:
        return None
    cur_amount = next((a.amount for a in current if a.currency == primary), 0.0)
    prev_amount = next((a.amount for a in previous if a.currency == primary), 0.0)
    if prev_amount == 0:
        return None
    return round((cur_amount - prev_amount) / prev_amount * 100.0, 1)


def _count_change_percent(current: int, previous: int) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100.0, 1)


def _build_kpi(
    current_rows: dict[str, dict],
    previous_rows: dict[str, dict],
    field: str,
) -> KpiCard:
    current = [
        CurrencyAmount(currency=cur, amount=float(row[field] or 0))
        for cur, row in current_rows.items()
        if (row[field] or 0) != 0
    ]
    previous = [
        CurrencyAmount(currency=cur, amount=float(row[field] or 0))
        for cur, row in previous_rows.items()
        if (row[field] or 0) != 0
    ]
    return KpiCard(
        current=current,
        previous=previous,
        change_percent=_change_percent(current, previous),
    )


async def _run_kpi_aggregate(
    db: AsyncSession,
    shop_id: uuid.UUID,
    start: date,
    end: date,
) -> dict[str, dict]:
    """Single round-trip per-currency aggregate for revenue/cost/fees/count/AOV/missing_cost.

    Returns a dict keyed by currency with raw aggregate values (Decimal/int).
    Net profit is computed in Python (revenue - cogs - fees) per-currency.
    """
    date_expr = func.coalesce(Order.shipped_at, Order.ordered_at)
    # MAT-5 Phase B: row-wise COALESCE(computed, manual, 0) before SUM —
    # each order contributes computed if present, else manual, else 0.
    effective_cost_expr = func.coalesce(
        Order.computed_production_cost, Order.production_cost, 0
    )
    stmt = (
        select(
            Order.currency.label("currency"),
            func.sum(Order.total_price).label("revenue"),
            func.sum(effective_cost_expr).label("cogs"),
            func.sum(
                func.coalesce(Order.platform_fee, 0)
                + func.coalesce(Order.shipping_np_cost, 0)
            ).label("fees"),
            func.count().label("order_count"),
            func.avg(Order.total_price).label("aov"),
            func.count()
            .filter(effective_cost_expr == 0)
            .label("missing_cost_count"),
            func.count()
            .filter(Order.computed_production_cost.is_not(None))
            .label("with_computed_cost_count"),
        )
        .where(Order.shop_id == shop_id)
        .where(Order.status.in_(REVENUE_STATUSES))
        .where(cast(date_expr, Date) >= start)
        .where(cast(date_expr, Date) <= end)
        .group_by(Order.currency)
    )
    result = await db.execute(stmt)
    rows: dict[str, dict] = {}
    for row in result.all():
        revenue = float(row.revenue or 0)
        cogs = float(row.cogs or 0)
        fees = float(row.fees or 0)
        rows[row.currency] = {
            "revenue": revenue,
            "cogs": cogs,
            "fees": fees,
            "order_count": int(row.order_count or 0),
            "aov": float(row.aov or 0),
            "missing_cost_count": int(row.missing_cost_count or 0),
            "with_computed_cost_count": int(row.with_computed_cost_count or 0),
        }
    return rows


async def _run_overhead_aggregate(
    db: AsyncSession,
    shop_id: uuid.UUID,
    start: date,
    end: date,
) -> dict[str, dict]:
    """Per-currency SUM(OverheadMaterialReceipt.total_cost) where shop_id = :shop_id."""
    stmt = (
        select(
            OverheadMaterialReceipt.currency.label("currency"),
            func.coalesce(func.sum(OverheadMaterialReceipt.total_cost), 0).label(
                "allocated_overhead"
            ),
        )
        .where(OverheadMaterialReceipt.shop_id == shop_id)
        .where(cast(OverheadMaterialReceipt.received_at, Date) >= start)
        .where(cast(OverheadMaterialReceipt.received_at, Date) <= end)
        .group_by(OverheadMaterialReceipt.currency)
    )
    result = await db.execute(stmt)
    return {
        row.currency: {"allocated_overhead": float(row.allocated_overhead or 0)}
        for row in result.all()
    }


async def _run_refunds_aggregate(
    db: AsyncSession,
    shop_id: uuid.UUID,
    start: date,
    end: date,
) -> dict[str, dict]:
    """Per-currency SUM(OrderRefund.amount) booked in [start, end] by REFUND date.

    SHOPIFY-REFUNDS / Model 2: refunds are dated by their own ``refunded_at`` (not the
    order's ship/order date), so a June order refunded in July reduces July, not June.
    Joined to Order and filtered to REVENUE_STATUSES so a refund nets only against the
    same order population that produced revenue — a cancelled+refunded order (excluded
    from revenue) is not double-subtracted.
    """
    stmt = (
        select(
            OrderRefund.currency.label("currency"),
            func.coalesce(func.sum(OrderRefund.amount), 0).label("refunds"),
        )
        .join(Order, OrderRefund.order_id == Order.id)
        .where(Order.shop_id == shop_id)
        .where(Order.status.in_(REVENUE_STATUSES))
        .where(cast(OrderRefund.refunded_at, Date) >= start)
        .where(cast(OrderRefund.refunded_at, Date) <= end)
        .group_by(OrderRefund.currency)
    )
    result = await db.execute(stmt)
    return {
        row.currency: {"refunds": float(row.refunds or 0)}
        for row in result.all()
    }


def _empty_kpi_row() -> dict:
    """A zeroed per-currency kpi row — used when overhead or refunds introduce a
    currency that had no orders in the period."""
    return {
        "revenue": 0.0,
        "cogs": 0.0,
        "fees": 0.0,
        "order_count": 0,
        "aov": 0.0,
        "missing_cost_count": 0,
        "with_computed_cost_count": 0,
    }


async def _run_product_only_aggregate(
    db: AsyncSession,
    shop_id: uuid.UUID,
    start: date,
    end: date,
) -> dict[str, dict]:
    """Per-currency aggregate for PART-1 product-only formulas.

    Differs from _run_kpi_aggregate in two ways:
      - revenue is SUM(OrderItem.quantity * OrderItem.unit_price) joined via
        a per-order subquery (avoids row multiplication on COGS/fees).
      - fees is platform_fee ONLY (shipping_np_cost excluded — partners
        contribute nothing to shipping logistics).
    """
    date_expr = func.coalesce(Order.shipped_at, Order.ordered_at)
    effective_cost_expr = func.coalesce(
        Order.computed_production_cost, Order.production_cost, 0
    )
    items_subq = (
        select(
            OrderItem.order_id.label("order_id"),
            func.sum(OrderItem.quantity * OrderItem.unit_price).label("items_subtotal"),
        )
        .group_by(OrderItem.order_id)
        .subquery()
    )
    stmt = (
        select(
            Order.currency.label("currency"),
            func.coalesce(func.sum(items_subq.c.items_subtotal), 0).label(
                "items_revenue"
            ),
            func.sum(effective_cost_expr).label("cogs"),
            func.coalesce(
                func.sum(func.coalesce(Order.platform_fee, 0)), 0
            ).label("non_shipping_fees"),
            # PARTNER-CONFIG-1: item discount funded by the shop. Additive — the
            # two legacy PART-1 formulas read only the three keys above and are
            # unaffected. NULL (Etsy/manual orders carry no discount figure)
            # reads as 0, so nothing moves for them. `shipping_discount` is
            # deliberately NOT included: shipping economics stay out of every
            # partner base.
            func.coalesce(
                func.sum(func.coalesce(Order.discount_total, 0)), 0
            ).label("discount_total"),
        )
        .select_from(Order)
        .join(items_subq, items_subq.c.order_id == Order.id, isouter=True)
        .where(Order.shop_id == shop_id)
        .where(Order.status.in_(REVENUE_STATUSES))
        .where(cast(date_expr, Date) >= start)
        .where(cast(date_expr, Date) <= end)
        .group_by(Order.currency)
    )
    result = await db.execute(stmt)
    return {
        row.currency: {
            "items_revenue": float(row.items_revenue or 0),
            "cogs": float(row.cogs or 0),
            "non_shipping_fees": float(row.non_shipping_fees or 0),
            "discount_total": float(getattr(row, "discount_total", 0) or 0),
        }
        for row in result.all()
    }


async def _run_shipping_aggregate(
    db: AsyncSession,
    shop_id: uuid.UUID,
    start: date,
    end: date,
) -> dict[str, dict]:
    """Per-currency shipping revenue and shipping cost for PART-1 KPI.

    shipping_revenue = SUM(total_price - items_subtotal_per_order)
    shipping_cost    = SUM(COALESCE(shipping_np_cost, 0))
    shipping_net     = shipping_revenue - shipping_cost

    ORDER-SHIPPING-1 note — this derivation is knowingly left in place. There is
    now a real `Order.shipping_revenue` column, and this residual is NOT it: it
    absorbs tax and discounts too (total_price is gross of tax and net of
    discount, while items_subtotal uses the PRE-discount unit price), and the
    COALESCE below books an item-less order's entire total as shipping. Switching
    the KPI to the stored column would move historical P&L figures, so it was
    scoped out deliberately and needs its own reconciliation sprint. Until then
    this card and the order card disagree on the same shop, by design.
    """
    date_expr = func.coalesce(Order.shipped_at, Order.ordered_at)
    items_subq = (
        select(
            OrderItem.order_id.label("order_id"),
            func.sum(OrderItem.quantity * OrderItem.unit_price).label("items_subtotal"),
        )
        .group_by(OrderItem.order_id)
        .subquery()
    )
    stmt = (
        select(
            Order.currency.label("currency"),
            func.coalesce(
                func.sum(
                    Order.total_price - func.coalesce(items_subq.c.items_subtotal, 0)
                ),
                0,
            ).label("shipping_revenue"),
            func.coalesce(
                func.sum(func.coalesce(Order.shipping_np_cost, 0)), 0
            ).label("shipping_cost"),
        )
        .select_from(Order)
        .join(items_subq, items_subq.c.order_id == Order.id, isouter=True)
        .where(Order.shop_id == shop_id)
        .where(Order.status.in_(REVENUE_STATUSES))
        .where(cast(date_expr, Date) >= start)
        .where(cast(date_expr, Date) <= end)
        .group_by(Order.currency)
    )
    result = await db.execute(stmt)
    rows: dict[str, dict] = {}
    for row in result.all():
        shipping_revenue = float(row.shipping_revenue or 0)
        shipping_cost = float(row.shipping_cost or 0)
        rows[row.currency] = {
            "shipping_revenue": shipping_revenue,
            "shipping_cost": shipping_cost,
            "shipping_net": shipping_revenue - shipping_cost,
        }
    return rows


async def compute_net_profit_product_only(
    db: AsyncSession,
    shop_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> list[CurrencyAmount]:
    """PART-1 partner profit-share base — excludes shipping economics.

    items_revenue - cogs - platform_fee - allocated_overhead, per currency.
    See docs/design/profit-definition.md §6 for the rationale.
    """
    kpi = await _run_product_only_aggregate(db, shop_id, period_start, period_end)
    overhead = await _run_overhead_aggregate(db, shop_id, period_start, period_end)
    merged: dict[str, float] = {}
    for currency, row in kpi.items():
        merged[currency] = (
            row["items_revenue"] - row["cogs"] - row["non_shipping_fees"]
        )
    for currency, row in overhead.items():
        merged[currency] = merged.get(currency, 0.0) - row["allocated_overhead"]
    return [
        CurrencyAmount(currency=c, amount=v)
        for c, v in merged.items()
        if v != 0
    ]


async def compute_revenue_items_minus_fees(
    db: AsyncSession,
    shop_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> list[CurrencyAmount]:
    """PART-1 revenue-share partner base — items revenue minus platform fees."""
    kpi = await _run_product_only_aggregate(db, shop_id, period_start, period_end)
    return [
        CurrencyAmount(
            currency=c,
            amount=r["items_revenue"] - r["non_shipping_fees"],
        )
        for c, r in kpi.items()
        if (r["items_revenue"] - r["non_shipping_fees"]) != 0
    ]


# ─── PARTNER-CONFIG-1 base terms ───────────────────────────
#
# The two new partner bases are returned as a TERM TABLE — one
# (name, source-currency, signed Decimal) per component — rather than a folded
# per-currency total. Two reasons:
#
#   1. The fold needs FX, and this module deliberately never imports fx_service.
#      Every aggregate here partitions by currency and stops; conversion policy
#      lives one layer up, in partner_payout_service, which already owns every
#      422 in the settlement flow. Keeping it that way is what lets the finance
#      page stay honestly FX-blind while a settlement is not.
#   2. The signed terms are what the settlement preview shows the operator, so
#      "why is my base this number" is answerable without re-running anything.
#
# Amounts are exact Decimals, never rounded here — the caller quantizes ONCE at
# the end of its fold (same convention as order_consumption_service).

#: One component of a partner base: (term name, source currency, signed amount).
BaseTermRow = tuple[str, str, Decimal]


def _term_rows_from_product_aggregate(
    rows: dict[str, dict], keys: tuple[tuple[str, int], ...]
) -> list[BaseTermRow]:
    """Expand a per-currency aggregate into signed term rows.

    `keys` pairs an aggregate key with its sign (+1 adds to the base, -1
    subtracts). Zero components are kept, not filtered: a term that exists and
    happens to be 0.00 is different from a term that does not exist, and the
    caller reports the full term table to the operator.
    """
    out: list[BaseTermRow] = []
    for currency, row in rows.items():
        for key, sign in keys:
            out.append((key, currency, Decimal(str(row.get(key, 0) or 0)) * sign))
    return out


async def compute_turnover_terms(
    db: AsyncSession,
    shop_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> list[BaseTermRow]:
    """TURNOVER base terms: items_revenue - discount - refunds.

    "Turnover" here is the gross item price the customer actually paid: before
    platform fees, before COGS, EXCLUDING shipping entirely (rule 2), and net of
    the discount the shop funded — paying a partner a share of a price nobody
    was charged is not turnover. Refunds are subtracted in the period the REFUND
    landed (Model 2), never by reopening a settled period.

    Built for exactly one partner today, but a first-class basis.
    """
    kpi = await _run_product_only_aggregate(db, shop_id, period_start, period_end)
    refunds = await _run_refunds_aggregate(db, shop_id, period_start, period_end)
    terms = _term_rows_from_product_aggregate(
        kpi, (("items_revenue", 1), ("discount_total", -1))
    )
    terms += [
        ("refunds", currency, Decimal(str(row["refunds"] or 0)) * -1)
        for currency, row in refunds.items()
    ]
    return terms


async def compute_profit_terms(
    db: AsyncSession,
    shop_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> list[BaseTermRow]:
    """PROFIT base terms: TURNOVER - COGS - non-shipping fees - allocated overhead.

    This is `NET_PROFIT_PRODUCT_ONLY` plus a refund term, minus the funded
    discount, with overhead FX-converted by the caller. It is NOT the Finance
    page's net profit, which also nets shipping economics — see
    docs/design/profit-definition.md §6, which this basis PRESERVES rather than
    reverses. NETPROFIT-RECONCILE is untouched by this sprint.

    Unallocated (NULL-shop) overhead stays out, exactly as in Finance today:
    `_run_overhead_aggregate` filters `shop_id = :shop_id`.
    """
    kpi = await _run_product_only_aggregate(db, shop_id, period_start, period_end)
    overhead = await _run_overhead_aggregate(db, shop_id, period_start, period_end)
    refunds = await _run_refunds_aggregate(db, shop_id, period_start, period_end)
    terms = _term_rows_from_product_aggregate(
        kpi,
        (
            ("items_revenue", 1),
            ("discount_total", -1),
            ("cogs", -1),
            ("non_shipping_fees", -1),
        ),
    )
    terms += [
        ("allocated_overhead", currency, Decimal(str(row["allocated_overhead"] or 0)) * -1)
        for currency, row in overhead.items()
    ]
    terms += [
        ("refunds", currency, Decimal(str(row["refunds"] or 0)) * -1)
        for currency, row in refunds.items()
    ]
    return terms


async def compute_base_quality(
    db: AsyncSession,
    shop: Shop,
    period_start: date,
    period_end: date,
) -> dict:
    """Data-readiness counts for a settlement period (PARTNER-CONFIG-1 rule 7).

    Warnings, never blocks. A partner base is only as honest as the data behind
    it, and the three things that silently overstate it are invisible in the
    number itself:

      (a) orders with no cost at all — same definition as the finance
          `diagnostic.orders_missing_cost`: COALESCE(computed, manual) = 0.
          Overstates a PROFIT base by the whole missing COGS.
      (b) closed calendar months with Etsy orders but no imported statement —
          fees are 0 until the statement lands, so the base is overstated.
      (c) Shopify orders with `platform_fee IS NULL` — the shop's rate was not
          set when they were imported. Fixed by the OWNER-only
          POST /api/shops/{id}/backfill-platform-fees, not by this sprint.

    Etsy refunds are not booked anywhere yet (ETSY-REFUNDS is out of scope), so
    an Etsy shop's refund deduction is structurally 0 — reported as a flag, not
    fixed here.

    (a) and (c) ride one query over the same order population the base itself
    scans; (b) is one extra query, Etsy shops only.
    """
    date_expr = func.coalesce(Order.shipped_at, Order.ordered_at)
    effective_cost_expr = func.coalesce(
        Order.computed_production_cost, Order.production_cost, 0
    )
    population = (
        Order.shop_id == shop.id,
        Order.status.in_(REVENUE_STATUSES),
        cast(date_expr, Date) >= period_start,
        cast(date_expr, Date) <= period_end,
    )
    counts = (
        await db.execute(
            select(
                func.count().label("total_orders"),
                func.count().filter(effective_cost_expr == 0).label("missing_cost"),
                func.count()
                .filter(Order.platform_fee.is_(None))
                .label("missing_platform_fee"),
            ).where(*population)
        )
    ).one()

    is_etsy = shop.platform == ShopPlatform.ETSY
    months_without_statement: list[str] = []
    if is_etsy:
        order_months = select(
            func.date_trunc("month", date_expr).cast(Date).label("m")
        ).where(*population).distinct()
        imported = select(EtsyStatementLine.period_month.label("m")).where(
            EtsyStatementLine.shop_id == shop.id
        ).distinct()
        rows = (await db.execute(order_months.except_(imported))).scalars().all()
        # Only CLOSED months warn — the current month has no statement yet by
        # definition, and flagging it would cry wolf on every preview.
        today = date.today()
        first_of_this_month = today.replace(day=1)
        months_without_statement = sorted(
            m.isoformat() for m in rows if m and m < first_of_this_month
        )

    return {
        "total_orders": int(counts.total_orders or 0),
        "orders_missing_cost": int(counts.missing_cost or 0),
        "orders_missing_platform_fee": int(counts.missing_platform_fee or 0),
        "etsy_months_without_statement": months_without_statement,
        "etsy_refunds_unbooked": is_etsy,
    }


async def compute_shipping_net(
    db: AsyncSession,
    shop_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> list[CurrencyAmount]:
    """PART-1 informational KPI: shipping_revenue - shipping_cost per currency.

    Auto-hide on FIN-1 is achieved by the _build_kpi zero-filter — empty
    list = no card rendered on the frontend.
    """
    rows = await _run_shipping_aggregate(db, shop_id, period_start, period_end)
    return [
        CurrencyAmount(currency=c, amount=r["shipping_net"])
        for c, r in rows.items()
        if r["shipping_net"] != 0
    ]


async def _run_pipeline_aggregate(
    db: AsyncSession,
    shop_id: uuid.UUID,
    start: date,
    end: date,
) -> dict[str, dict]:
    """Pipeline-value aggregate — sum of total_price over non-terminal orders."""
    date_expr = func.coalesce(Order.shipped_at, Order.ordered_at)
    stmt = (
        select(
            Order.currency.label("currency"),
            func.sum(Order.total_price).label("pipeline_value"),
        )
        .where(Order.shop_id == shop_id)
        .where(Order.status.not_in(PIPELINE_EXCLUDED_STATUSES))
        .where(cast(date_expr, Date) >= start)
        .where(cast(date_expr, Date) <= end)
        .group_by(Order.currency)
    )
    result = await db.execute(stmt)
    return {
        row.currency: {"pipeline_value": float(row.pipeline_value or 0)}
        for row in result.all()
    }


async def _run_time_series(
    db: AsyncSession,
    shop_id: uuid.UUID,
    start: date,
    end: date,
    granularity: str,
) -> list[TimeSeriesPoint]:
    date_expr = func.coalesce(Order.shipped_at, Order.ordered_at)
    if granularity == "day":
        bucket = cast(date_expr, Date)
    else:
        bucket = cast(func.date_trunc("month", date_expr), Date)

    stmt = (
        select(
            bucket.label("bucket"),
            Order.currency.label("currency"),
            func.sum(Order.total_price).label("revenue"),
            func.sum(
                Order.total_price
                # MAT-5: COGS must match the KPI aggregate (computed-first, then manual).
                - func.coalesce(Order.computed_production_cost, Order.production_cost, 0)
                - func.coalesce(Order.platform_fee, 0)
                - func.coalesce(Order.shipping_np_cost, 0)
            ).label("net_profit"),
        )
        .where(Order.shop_id == shop_id)
        .where(Order.status.in_(REVENUE_STATUSES))
        .where(cast(date_expr, Date) >= start)
        .where(cast(date_expr, Date) <= end)
        .group_by(bucket, Order.currency)
        .order_by(bucket)
    )
    result = await db.execute(stmt)
    # Accumulate into a keyed map so refunds (dated by their own refunded_at) can be
    # netted into the matching bucket+currency — SHOPIFY-REFUNDS Model 2. A bucket with
    # only refunds (no orders) still surfaces, as a negative net_profit point.
    points_by_key: dict[tuple[str, str], dict] = {}
    for row in result.all():
        bucket_val = row.bucket
        date_str = (
            bucket_val.isoformat() if hasattr(bucket_val, "isoformat") else str(bucket_val)
        )
        points_by_key[(date_str, row.currency)] = {
            "revenue": float(row.revenue or 0),
            "net_profit": float(row.net_profit or 0),
        }

    # Refunds bucketed by refunded_at at the same granularity, same order population.
    refund_bucket = (
        cast(OrderRefund.refunded_at, Date)
        if granularity == "day"
        else cast(func.date_trunc("month", OrderRefund.refunded_at), Date)
    )
    refund_stmt = (
        select(
            refund_bucket.label("bucket"),
            OrderRefund.currency.label("currency"),
            func.sum(OrderRefund.amount).label("refunds"),
        )
        .join(Order, OrderRefund.order_id == Order.id)
        .where(Order.shop_id == shop_id)
        .where(Order.status.in_(REVENUE_STATUSES))
        .where(cast(OrderRefund.refunded_at, Date) >= start)
        .where(cast(OrderRefund.refunded_at, Date) <= end)
        .group_by(refund_bucket, OrderRefund.currency)
    )
    refund_result = await db.execute(refund_stmt)
    for row in refund_result.all():
        bucket_val = row.bucket
        date_str = (
            bucket_val.isoformat() if hasattr(bucket_val, "isoformat") else str(bucket_val)
        )
        point = points_by_key.setdefault(
            (date_str, row.currency), {"revenue": 0.0, "net_profit": 0.0}
        )
        point["net_profit"] -= float(row.refunds or 0)

    points = [
        TimeSeriesPoint(
            date=date_str,
            currency=currency,
            revenue=data["revenue"],
            net_profit=data["net_profit"],
        )
        for (date_str, currency), data in points_by_key.items()
    ]
    points.sort(key=lambda p: (p.date, p.currency))
    return points


async def get_shop_finance(
    db: AsyncSession,
    shop_id: uuid.UUID,
    start_date: date,
    end_date: date,
) -> ShopFinanceResponse:
    """Compute the per-shop financial overview for a custom period.

    Raises 404 if the shop doesn't exist or has been soft-deleted.
    Raises 422 if start_date > end_date.
    """
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be on or before end_date",
        )

    shop_result = await db.execute(
        select(Shop).where(Shop.id == shop_id, Shop.is_active == True)  # noqa: E712
    )
    shop = shop_result.scalar_one_or_none()
    if shop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found",
        )

    granularity = "day" if (end_date - start_date).days <= 90 else "month"
    prev_start, prev_end = _previous_period(start_date, end_date)

    current_rows = await _run_kpi_aggregate(db, shop_id, start_date, end_date)
    previous_rows = await _run_kpi_aggregate(db, shop_id, prev_start, prev_end)
    overhead_current = await _run_overhead_aggregate(db, shop_id, start_date, end_date)
    overhead_previous = await _run_overhead_aggregate(db, shop_id, prev_start, prev_end)
    refunds_current = await _run_refunds_aggregate(db, shop_id, start_date, end_date)
    refunds_previous = await _run_refunds_aggregate(db, shop_id, prev_start, prev_end)
    pipeline_current = await _run_pipeline_aggregate(db, shop_id, start_date, end_date)
    pipeline_previous = await _run_pipeline_aggregate(db, shop_id, prev_start, prev_end)
    shipping_current = await _run_shipping_aggregate(db, shop_id, start_date, end_date)
    shipping_previous = await _run_shipping_aggregate(db, shop_id, prev_start, prev_end)
    time_series = await _run_time_series(db, shop_id, start_date, end_date, granularity)

    # MAT-5 / SHOPIFY-REFUNDS: merge per-currency overhead + refunds into the kpi-row
    # dicts so a currency that only has overhead or only has refunds (no orders in this
    # period) still appears in net_profit. Refunds are dated by their own refunded_at
    # (Model 2), so they land in the period they occurred, not the order's month.
    for overhead_src, refunds_src, target in (
        (overhead_current, refunds_current, current_rows),
        (overhead_previous, refunds_previous, previous_rows),
    ):
        for currency, row in overhead_src.items():
            target.setdefault(currency, _empty_kpi_row())["allocated_overhead"] = row[
                "allocated_overhead"
            ]
        for currency, row in refunds_src.items():
            target.setdefault(currency, _empty_kpi_row())["refunds"] = row["refunds"]
        # Fill default 0 for currencies missing either subtractive term.
        for row in target.values():
            row.setdefault("allocated_overhead", 0.0)
            row.setdefault("refunds", 0.0)
        # Compute net_profit per-currency after all subtractive terms are known.
        for row in target.values():
            row["net_profit"] = (
                row["revenue"]
                - row["cogs"]
                - row["fees"]
                - row["allocated_overhead"]
                - row["refunds"]
            )

    revenue = _build_kpi(current_rows, previous_rows, "revenue")
    cogs = _build_kpi(current_rows, previous_rows, "cogs")
    fees = _build_kpi(current_rows, previous_rows, "fees")
    allocated_overhead_expenses = _build_kpi(
        current_rows, previous_rows, "allocated_overhead"
    )
    refunds = _build_kpi(current_rows, previous_rows, "refunds")
    net_profit = _build_kpi(current_rows, previous_rows, "net_profit")
    aov = _build_kpi(current_rows, previous_rows, "aov")
    pipeline_value = _build_kpi(pipeline_current, pipeline_previous, "pipeline_value")
    shipping_net = _build_kpi(shipping_current, shipping_previous, "shipping_net")

    current_count = sum(r["order_count"] for r in current_rows.values())
    previous_count = sum(r["order_count"] for r in previous_rows.values())
    order_count = OrderCountCard(
        current=current_count,
        previous=previous_count,
        change_percent=_count_change_percent(current_count, previous_count),
    )

    diagnostic = DiagnosticInfo(
        orders_missing_cost=sum(r["missing_cost_count"] for r in current_rows.values()),
        total_orders_in_period=current_count,
        orders_with_computed_cost=sum(
            r["with_computed_cost_count"] for r in current_rows.values()
        ),
    )

    return ShopFinanceResponse(
        shop_id=str(shop.id),
        shop_name=shop.name,
        period_start_iso=start_date.isoformat(),
        period_end_iso=end_date.isoformat(),
        granularity=granularity,
        revenue=revenue,
        cogs=cogs,
        fees=fees,
        allocated_overhead_expenses=allocated_overhead_expenses,
        refunds=refunds,
        net_profit=net_profit,
        pipeline_value=pipeline_value,
        order_count=order_count,
        aov=aov,
        time_series=time_series,
        diagnostic=diagnostic,
        shipping_net=shipping_net,
    )
