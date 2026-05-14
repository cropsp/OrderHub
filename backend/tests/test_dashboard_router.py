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
import uuid
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
