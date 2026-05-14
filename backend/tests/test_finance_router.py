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
