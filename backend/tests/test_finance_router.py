"""FIN-1 — Per-shop financial overview endpoint regression-guards.

Mirrors the compile-SQL pattern from test_dashboard_router.py (added in
DASH-REVENUE-DATE, commit a552c39). The codebase has no real-DB test
fixture, so we capture the issued statements via a mocked db.execute,
compile them to SQL, and check the WHERE / GROUP BY shape there.

Two regression-guards:
  1. Time-series and KPI queries must group/filter on
     COALESCE(shipped_at, ordered_at) — per FIN-1 rule #3 (and the
     fix the dashboard test already guards).
  2. Revenue/cost/fee aggregates must filter to status IN
     ('shipped', 'completed') — per FIN-1 rule #1.
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from services.finance_service import get_shop_finance


def _make_db_with_shop():
    """Build a mocked AsyncSession that returns a fake active shop on the
    first execute() and empty result rows for every aggregate query after.

    Returns (db, captured) where `captured` accumulates every SQL statement
    issued through db.execute so the test can compile them and assert on
    the resulting SQL string.
    """
    captured: list = []
    shop = MagicMock()
    shop.id = uuid.uuid4()
    shop.name = "Test Shop"

    call_count = {"n": 0}

    async def fake_execute(stmt):
        captured.append(stmt)
        call_count["n"] += 1
        r = MagicMock()
        if call_count["n"] == 1:
            # First execute() in get_shop_finance is the shop-existence
            # check; return the fake shop so the function proceeds.
            r.scalar_one_or_none.return_value = shop
        else:
            r.scalar_one_or_none.return_value = None
        r.all.return_value = []
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    return db, captured, shop


def _compiled_sqls(captured) -> list[str]:
    return [
        str(s.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()
        for s in captured
    ]


@pytest.mark.asyncio
async def test_finance_endpoint_uses_coalesce_for_grouping():
    """Per FIN-1 rule #3, every aggregate must use COALESCE(shipped_at, ordered_at)."""
    db, captured, shop = _make_db_with_shop()

    await get_shop_finance(
        db=db,
        shop_id=shop.id,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 14),
    )

    sqls = _compiled_sqls(captured)
    assert any(
        "coalesce(orders.shipped_at, orders.ordered_at)" in s for s in sqls
    ), (
        "Finance queries do not use COALESCE(shipped_at, ordered_at). "
        f"Captured SQL: {sqls}"
    )


@pytest.mark.asyncio
async def test_finance_endpoint_filters_revenue_to_shipped_completed():
    """Per FIN-1 rule #1, the KPI/time-series queries must filter to
    status IN ('shipped', 'completed'). The pipeline query is the
    exception (uses NOT IN), but at least one revenue query must hit
    the IN clause."""
    db, captured, shop = _make_db_with_shop()

    await get_shop_finance(
        db=db,
        shop_id=shop.id,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 14),
    )

    sqls = _compiled_sqls(captured)
    # The compiled enum IN clause renders as `orders.status in ('shipped', 'completed')`
    # under the postgresql dialect with literal_binds=True. Match the substring
    # robustly: both values must appear in the same IN clause.
    assert any(
        "orders.status in ('shipped', 'completed')" in s for s in sqls
    ), (
        "No revenue query filters status IN ('shipped', 'completed'). "
        f"Captured SQL: {sqls}"
    )


@pytest.mark.asyncio
async def test_finance_cogs_uses_coalesce_of_computed_and_manual():
    """MAT-5 Phase B: COGS aggregation must apply COALESCE(computed, manual)
    row-wise before SUM, so an order with a BOM-computed cost contributes
    that value, falling back to manual production_cost only when computed
    is NULL.
    """
    db, captured, shop = _make_db_with_shop()

    await get_shop_finance(
        db=db,
        shop_id=shop.id,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 14),
    )

    sqls = _compiled_sqls(captured)
    assert any(
        "coalesce(orders.computed_production_cost, orders.production_cost" in s
        for s in sqls
    ), (
        "COGS aggregation does not COALESCE computed_production_cost with "
        f"production_cost (Phase B cutover). Captured SQL: {sqls}"
    )


@pytest.mark.asyncio
async def test_finance_overhead_aggregate_filters_by_shop_id():
    """MAT-5: per-shop overhead aggregate must filter by
    overhead_material_receipts.shop_id = :shop_id and group by currency.
    """
    db, captured, shop = _make_db_with_shop()

    await get_shop_finance(
        db=db,
        shop_id=shop.id,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 14),
    )

    sqls = _compiled_sqls(captured)
    overhead_sqls = [
        s for s in sqls if "overhead_material_receipts" in s
    ]
    assert overhead_sqls, (
        "No overhead aggregate query was issued. "
        f"Captured SQL: {sqls}"
    )
    assert any(
        "overhead_material_receipts.shop_id =" in s for s in overhead_sqls
    ), (
        "Overhead aggregate does not filter by shop_id. "
        f"Captured SQL: {overhead_sqls}"
    )
    assert any(
        "group by overhead_material_receipts.currency" in s
        for s in overhead_sqls
    ), (
        "Overhead aggregate is not grouped by currency. "
        f"Captured SQL: {overhead_sqls}"
    )


# ─── PART-1 additions ──────────────────────────────────────────────────

from services.finance_service import (  # noqa: E402
    compute_net_profit_product_only,
    compute_shipping_net,
)
from schemas.finance import CurrencyAmount  # noqa: E402


@pytest.mark.asyncio
async def test_get_shop_finance_includes_shipping_aggregate_query():
    """PART-1: get_shop_finance must invoke the shipping aggregate so
    response.shipping_net is populated."""
    db, captured, shop = _make_db_with_shop()
    await get_shop_finance(
        db=db,
        shop_id=shop.id,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
    )
    sqls = _compiled_sqls(captured)
    shipping_sqls = [
        s for s in sqls
        if "shipping_np_cost" in s and "total_price - coalesce" in s
    ]
    assert shipping_sqls, (
        "No shipping_net aggregate query was issued. "
        f"Captured SQL: {sqls}"
    )


@pytest.mark.asyncio
async def test_compute_net_profit_product_only_sql_excludes_shipping():
    """PART-1: SQL must NOT include shipping_np_cost (partners don't
    share in shipping). Must JOIN order_items via subquery."""
    db, captured, _ = _make_db_with_shop()
    await compute_net_profit_product_only(
        db=db,
        shop_id=uuid.uuid4(),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    sqls = _compiled_sqls(captured)
    product_only_sql = next(
        (s for s in sqls if "items_subtotal" in s or "quantity * order_items" in s),
        None,
    )
    assert product_only_sql is not None, (
        f"Product-only aggregate SQL was not issued. SQL: {sqls}"
    )
    assert "shipping_np_cost" not in product_only_sql, (
        "Product-only aggregate must NOT reference shipping_np_cost. "
        f"SQL: {product_only_sql}"
    )
    assert "platform_fee" in product_only_sql


@pytest.mark.asyncio
async def test_compute_shipping_net_returns_empty_list_when_zero():
    """PART-1 auto-hide: when the SUM is zero (or no orders), shipping_net
    returns an empty list — frontend uses that to skip rendering the card."""
    db, _, _ = _make_db_with_shop()  # mocks return empty .all() rows
    result = await compute_shipping_net(
        db=db,
        shop_id=uuid.uuid4(),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    assert isinstance(result, list)
    assert result == []  # no shipping data → empty list → KPI auto-hides


# ── SHOPIFY-REFUNDS (Model 2) ──────────────────────────────

@pytest.mark.asyncio
async def test_finance_refunds_aggregate_shape():
    """The refunds aggregate must SUM(order_refunds.amount), join to orders,
    filter status IN ('shipped','completed') and GROUP BY the refund currency."""
    db, captured, shop = _make_db_with_shop()

    await get_shop_finance(
        db=db, shop_id=shop.id,
        start_date=date(2026, 7, 1), end_date=date(2026, 7, 31),
    )

    sqls = _compiled_sqls(captured)
    refund_sql = next((s for s in sqls if "sum(order_refunds.amount)" in s), None)
    assert refund_sql is not None, f"No refunds aggregate issued. SQL: {sqls}"
    # Same order population as revenue (revenue-status netting), joined to orders.
    assert "join orders on order_refunds.order_id = orders.id" in refund_sql
    assert "orders.status in ('shipped', 'completed')" in refund_sql
    assert "group by order_refunds.currency" in refund_sql


@pytest.mark.asyncio
async def test_finance_refunds_dated_by_refunded_at_not_order_date():
    """Model-2 crux: refunds are filtered/dated by their OWN refunded_at, NOT by the
    order's COALESCE(shipped_at, ordered_at). This is what makes a June order refunded
    in July reduce July, not June."""
    db, captured, shop = _make_db_with_shop()

    await get_shop_finance(
        db=db, shop_id=shop.id,
        start_date=date(2026, 7, 1), end_date=date(2026, 7, 31),
    )

    sqls = _compiled_sqls(captured)
    refund_sql = next((s for s in sqls if "sum(order_refunds.amount)" in s), None)
    assert refund_sql is not None, f"No refunds aggregate issued. SQL: {sqls}"
    # Dated by the refund's own date …
    assert "cast(order_refunds.refunded_at as date)" in refund_sql
    # … never by the order's ship/order date (that would be Model 1).
    assert "coalesce(orders.shipped_at, orders.ordered_at)" not in refund_sql

