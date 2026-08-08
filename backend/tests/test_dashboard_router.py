"""DASH-REVENUE-DATE — Revenue trend groups by COALESCE(shipped_at, ordered_at).

The fix at backend/routers/dashboard.py:90 swaps the daily-trend GROUP BY
from `cast(Order.ordered_at, Date)` to
`cast(func.coalesce(Order.shipped_at, Order.ordered_at), Date)` so that
revenue is plotted on the day a shipment went out rather than the day the
order was created. This regression-guards that change by compiling the
queries the router issues and asserting one of them contains the COALESCE
expression.

The codebase has no real-DB test fixture (every backend/tests/*.py mocks
the AsyncSession), so we capture the issued statements via a mocked
db.execute, compile them to SQL, and check the GROUP BY shape there.
"""
import re
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from models.user import UserRole
from routers.dashboard import get_dashboard_stats


@pytest.mark.asyncio
async def test_daily_revenue_trend_groups_by_coalesce_shipped_ordered():
    """Trend query must group by COALESCE(shipped_at, ordered_at), not ordered_at alone."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = UserRole.OWNER
    user.email = "owner@example.com"

    captured = []

    async def fake_execute(stmt):
        captured.append(stmt)
        r = MagicMock()
        r.all.return_value = []
        r.scalar_one_or_none.return_value = None
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.scalar = AsyncMock(return_value=0)

    await get_dashboard_stats(shop_id=None, current_user=user, db=db)

    sqls = [
        str(s.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()
        for s in captured
    ]
    assert any("coalesce(orders.shipped_at, orders.ordered_at)" in s for s in sqls), (
        "Trend query does not group by COALESCE(shipped_at, ordered_at). "
        f"Captured SQL: {sqls}"
    )


@pytest.mark.asyncio
async def test_dashboard_unallocated_overhead_filters_shop_id_null():
    """MAT-5: unallocated overhead aggregate must filter
    overhead_material_receipts.shop_id IS NULL so workshop-wide receipts
    surface on the global dashboard card.
    """
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = UserRole.OWNER
    user.email = "owner@example.com"

    captured = []

    async def fake_execute(stmt):
        captured.append(stmt)
        r = MagicMock()
        r.all.return_value = []
        r.scalar_one_or_none.return_value = None
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.scalar = AsyncMock(return_value=0)

    await get_dashboard_stats(shop_id=None, current_user=user, db=db)

    sqls = [
        str(s.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()
        for s in captured
    ]
    overhead_sqls = [s for s in sqls if "overhead_material_receipts" in s]
    assert overhead_sqls, (
        f"No overhead aggregate query was issued. Captured SQL: {sqls}"
    )
    assert any(
        "overhead_material_receipts.shop_id is null" in s for s in overhead_sqls
    ), (
        "Unallocated overhead query does not filter shop_id IS NULL. "
        f"Captured SQL: {overhead_sqls}"
    )


# --- DASH-PERIOD ---------------------------------------------------------
#
# The dashboard endpoint takes optional start_date/end_date. Financial widgets
# scope to the window; the operational ones (status counts / attention /
# low-stock) must stay all-time. Same compile-SQL approach as above — there is
# no real-DB fixture in this suite.

PERIOD_START = date(2026, 3, 1)
PERIOD_END = date(2026, 3, 31)


async def _capture_dashboard_sql(**kwargs) -> list[str]:
    """Run the endpoint against a mocked session; return the issued SQL, lower-cased."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = UserRole.OWNER
    user.email = "owner@example.com"

    captured = []

    async def fake_execute(stmt):
        captured.append(stmt)
        r = MagicMock()
        r.all.return_value = []
        r.scalar_one_or_none.return_value = None
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.scalar = AsyncMock(return_value=0)

    await get_dashboard_stats(shop_id=None, current_user=user, db=db, **kwargs)

    return [
        str(s.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()
        for s in captured
    ]


def _revenue_summary_sql(sqls: list[str]) -> str:
    # The per-currency summary groups by currency; the trend is the ordered one.
    matches = [
        s for s in sqls if "group by orders.currency" in s and "order by" not in s
    ]
    assert len(matches) == 1, f"Expected 1 revenue summary query, got {len(matches)}: {sqls}"
    return matches[0]


def _trend_sql(sqls: list[str]) -> str:
    matches = [s for s in sqls if "order by" in s and "orders.total_price" in s]
    assert len(matches) == 1, f"Expected 1 trend query, got {len(matches)}: {sqls}"
    return matches[0]


def _status_sql(sqls: list[str]) -> str:
    matches = [s for s in sqls if "group by orders.status" in s]
    assert len(matches) == 1, f"Expected 1 status query, got {len(matches)}: {sqls}"
    return matches[0]


@pytest.mark.asyncio
async def test_period_scopes_revenue_summary_and_trend_by_accrual_date():
    """Revenue summary + trend bound by COALESCE(shipped_at, ordered_at) within [start, end].

    Mirrors finance_service._run_kpi_aggregate's date expression so the dashboard
    and the Finance page reconcile for the same (shop, period).
    """
    sqls = await _capture_dashboard_sql(start_date=PERIOD_START, end_date=PERIOD_END)

    for label, sql in (("revenue summary", _revenue_summary_sql(sqls)), ("trend", _trend_sql(sqls))):
        assert "coalesce(orders.shipped_at, orders.ordered_at)" in sql, (
            f"{label} query does not use the accrual date column. SQL: {sql}"
        )
        assert "'2026-03-01'" in sql and "'2026-03-31'" in sql, (
            f"{label} query is not bounded by both period dates. SQL: {sql}"
        )


@pytest.mark.asyncio
async def test_period_trend_drops_the_hard_coded_thirty_day_window():
    """With an explicit period the trend must not also carry the 30-day fallback bound."""
    sqls = await _capture_dashboard_sql(start_date=PERIOD_START, end_date=PERIOD_END)
    trend = _trend_sql(sqls)

    dates_in_trend = set(re.findall(r"'(\d{4}-\d{2}-\d{2})[^']*'", trend))
    assert dates_in_trend == {"2026-03-01", "2026-03-31"}, (
        "Trend query carries a date bound other than the requested period — the "
        f"30-day fallback likely survived. Dates found: {dates_in_trend}. SQL: {trend}"
    )


@pytest.mark.asyncio
async def test_period_scopes_shop_distribution_by_ordered_at_and_overhead_by_received_at():
    """Shop distribution counts orders *placed* in the window; overhead uses received_at."""
    sqls = await _capture_dashboard_sql(start_date=PERIOD_START, end_date=PERIOD_END)

    shop_sqls = [s for s in sqls if "shops.name" in s]
    assert len(shop_sqls) == 1, f"Expected 1 shop distribution query: {sqls}"
    shop_sql = shop_sqls[0]
    assert "cast(orders.ordered_at as date) >= '2026-03-01'" in shop_sql, (
        f"Shop distribution not scoped by ordered_at. SQL: {shop_sql}"
    )
    assert "cast(orders.ordered_at as date) <= '2026-03-31'" in shop_sql, (
        f"Shop distribution not scoped by ordered_at. SQL: {shop_sql}"
    )
    assert "coalesce(orders.shipped_at" not in shop_sql, (
        "Shop distribution is an order count, not revenue — it must use ordered_at, "
        f"not the accrual column. SQL: {shop_sql}"
    )

    overhead_sqls = [s for s in sqls if "overhead_material_receipts" in s]
    assert len(overhead_sqls) == 1, f"Expected 1 overhead query: {sqls}"
    overhead_sql = overhead_sqls[0]
    assert "overhead_material_receipts.shop_id is null" in overhead_sql, (
        f"Overhead query lost its unallocated filter. SQL: {overhead_sql}"
    )
    assert "cast(overhead_material_receipts.received_at as date) >= '2026-03-01'" in overhead_sql, (
        f"Overhead not scoped by received_at. SQL: {overhead_sql}"
    )
    assert "cast(overhead_material_receipts.received_at as date) <= '2026-03-31'" in overhead_sql, (
        f"Overhead not scoped by received_at. SQL: {overhead_sql}"
    )


@pytest.mark.asyncio
async def test_operational_widgets_stay_live_regardless_of_period():
    """Status counts / attention drive the 'what needs action now' queue.

    Their query must be byte-identical with and without a period — this is the
    regression guard for settled rule #3.
    """
    without_period = _status_sql(await _capture_dashboard_sql())
    with_period = _status_sql(
        await _capture_dashboard_sql(start_date=PERIOD_START, end_date=PERIOD_END)
    )

    assert with_period == without_period, (
        "The status/attention query changed when a period was supplied — the "
        "operational queue must stay all-time.\n"
        f"without: {without_period}\nwith:    {with_period}"
    )


@pytest.mark.asyncio
async def test_no_dates_keeps_all_time_behaviour():
    """Backward-compat: no dates → unscoped financials + the 30-day trend fallback."""
    sqls = await _capture_dashboard_sql()

    revenue = _revenue_summary_sql(sqls)
    assert "coalesce(orders.shipped_at, orders.ordered_at)" not in revenue, (
        f"Revenue summary gained a date filter without a period. SQL: {revenue}"
    )

    trend = _trend_sql(sqls)
    assert "cast(coalesce(orders.shipped_at, orders.ordered_at) as date) >=" in trend, (
        f"Trend lost its 30-day fallback window. SQL: {trend}"
    )

    shop_sql = next(s for s in sqls if "shops.name" in s)
    assert "ordered_at as date" not in shop_sql, (
        f"Shop distribution gained a date filter without a period. SQL: {shop_sql}"
    )


# ── SHOPIFY-REFUNDS (Model 2) ──────────────────────────────

def _refund_sql(sqls: list[str]) -> str:
    matches = [s for s in sqls if "sum(order_refunds.amount)" in s]
    assert len(matches) == 1, f"Expected 1 refund query, got {len(matches)}: {sqls}"
    return matches[0]


@pytest.mark.asyncio
async def test_dashboard_refunds_query_shape_and_dates_by_refunded_at():
    """The dashboard refund aggregate mirrors finance: SUM(order_refunds.amount),
    joined to orders, filtered to shipped/completed, grouped by currency, and dated by
    the refund's own refunded_at (Model 2) within the period."""
    sqls = await _capture_dashboard_sql(start_date=PERIOD_START, end_date=PERIOD_END)

    refund = _refund_sql(sqls)
    assert "join orders on order_refunds.order_id = orders.id" in refund
    assert "orders.status in ('completed', 'shipped')" in refund
    assert "group by order_refunds.currency" in refund
    # Dated by refunded_at within the period — not the order's ship/order date.
    assert "cast(order_refunds.refunded_at as date) >= '2026-03-01'" in refund
    assert "cast(order_refunds.refunded_at as date) <= '2026-03-31'" in refund


@pytest.mark.asyncio
async def test_dashboard_refunds_all_time_has_no_date_filter():
    """No period → all-time refunds (matches the all-time revenue behaviour)."""
    sqls = await _capture_dashboard_sql()
    refund = _refund_sql(sqls)
    assert "order_refunds.refunded_at" not in refund, (
        f"Refund summary gained a date filter without a period. SQL: {refund}"
    )


# ---------------------------------------------------------------------------
# WH-2 — the low-stock packaging card reads materials, not boxes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_low_stock_card_counts_packaging_materials():
    """PKG-2 counted packaging_boxes against their own threshold columns. WH-2
    dropped both columns, so the card reads the paired materials instead — the
    same question, a different table. The count goes through db.scalar (not
    db.execute), so it is captured separately from the trend queries above.

    Also pinned: the two conditions the box-based query could not express. An
    archived box must not nag, and an untracked material's counter never moves,
    so comparing it to a threshold would leave the card stuck on forever.
    """
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = UserRole.OWNER
    user.email = "owner@example.com"

    scalars = []

    async def fake_execute(stmt):
        r = MagicMock()
        r.all.return_value = []
        r.scalar_one_or_none.return_value = None
        return r

    async def fake_scalar(stmt):
        scalars.append(stmt)
        return 3

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.scalar = AsyncMock(side_effect=fake_scalar)

    response = await get_dashboard_stats(shop_id=None, current_user=user, db=db)

    sqls = [
        str(s.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()
        for s in scalars
    ]
    low_stock_sql = next(
        (s for s in sqls if "low_stock_threshold" in s), None
    )
    assert low_stock_sql is not None, f"no low-stock count issued; got {sqls}"

    assert "from materials" in low_stock_sql
    assert "packaging_boxes" not in low_stock_sql, (
        "the box columns are gone — reading them would be a migration-time crash"
    )
    assert "materials.category = 'packaging'" in low_stock_sql
    assert "materials.stock_quantity <= materials.low_stock_threshold" in low_stock_sql
    assert "materials.is_active is true" in low_stock_sql
    assert "materials.is_stock_tracked is true" in low_stock_sql

    # The response field name is unchanged, so no frontend type moves.
    assert response.low_stock_packaging_count == 3
