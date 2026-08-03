"""SHOP-FEE-1 — one-time re-pricing of orders that never got a platform_fee.

Guards the eligibility predicate (never overwrite a set fee, never price a
cancelled order), the date bound (must match the expression finance buckets by,
or the reported total will not reconcile with the finance page), and the dry-run
contract (reports impact, writes nothing).

Mock-session style, as elsewhere in this suite: the SELECT and UPDATE statements
are compiled to strings and inspected, so the predicate itself is what is under
test rather than a stubbed result.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from models.order import OrderStatus
from services.order_service import backfill_platform_fees


# ---------- helpers ----------


def _make_shop(fee_percent=Decimal("8.00")):
    shop = MagicMock()
    shop.id = uuid4()
    shop.fee_percent = fee_percent
    return shop


def _row(*, total_price="100.00", currency="USD", status=OrderStatus.COMPLETED):
    row = MagicMock()
    row.id = uuid4()
    row.total_price = Decimal(total_price)
    row.currency = currency
    row.status = status
    return row


def _make_db(rows):
    """Session returning `rows` from the eligibility SELECT and recording every
    compiled statement so the predicates can be asserted on."""
    db = MagicMock()
    db.flush = AsyncMock()
    db.compiled = []

    async def execute(stmt):
        db.compiled.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        result = MagicMock()
        result.all.return_value = rows
        result.rowcount = 1
        return result

    db.execute = AsyncMock(side_effect=execute)
    return db


def _selects(db):
    return [s for s in db.compiled if s.lstrip().upper().startswith("SELECT")]


def _updates(db):
    return [s for s in db.compiled if s.lstrip().upper().startswith("UPDATE")]


# ---------- eligibility predicate ----------


@pytest.mark.asyncio
async def test_only_targets_orders_without_a_fee():
    """Rule 3: a fee a human entered is never overwritten. The NULL guard sits in
    BOTH the SELECT and the UPDATE, so a fee entered between the two can't be
    clobbered either."""
    db = _make_db([_row()])
    await backfill_platform_fees(db, _make_shop(), dry_run=False)

    assert "platform_fee IS NULL" in _selects(db)[0]
    assert _updates(db), "expected a real run to issue an UPDATE"
    assert "platform_fee IS NULL" in _updates(db)[0]


@pytest.mark.asyncio
async def test_excludes_cancelled_orders():
    db = _make_db([_row()])
    await backfill_platform_fees(db, _make_shop(), dry_run=True)
    assert "CANCELLED" in _selects(db)[0]


@pytest.mark.asyncio
async def test_noop_when_shop_has_no_rate():
    """A shop with no rate has nothing to backfill — and must not be given 0.00
    fees, which would make its orders permanently ineligible."""
    db = _make_db([_row()])
    summary = await backfill_platform_fees(db, _make_shop(fee_percent=None), dry_run=False)

    assert summary["matched"] == 0
    assert summary["updated"] == 0
    assert db.execute.await_count == 0


# ---------- date bounding ----------


@pytest.mark.asyncio
async def test_date_bound_uses_shipped_at_falling_back_to_ordered_at():
    """Must be the same expression finance buckets by (COALESCE(shipped_at,
    ordered_at)), or the reported total won't reconcile against the finance-page
    delta and the window won't line up with settlement periods."""
    db = _make_db([_row()])
    await backfill_platform_fees(
        db, _make_shop(), since=date(2026, 1, 1), until=date(2026, 6, 30), dry_run=True
    )

    sql = _selects(db)[0]
    assert "coalesce" in sql.lower()
    assert "shipped_at" in sql and "ordered_at" in sql
    assert "2026-01-01" in sql and "2026-06-30" in sql


@pytest.mark.asyncio
async def test_unbounded_run_applies_no_date_filter():
    db = _make_db([_row()])
    await backfill_platform_fees(db, _make_shop(), dry_run=True)

    sql = _selects(db)[0]
    assert "platform_fee IS NULL" in sql
    assert "shipped_at" not in sql


# ---------- dry run ----------


@pytest.mark.asyncio
async def test_dry_run_reports_but_writes_nothing():
    db = _make_db([_row(total_price="100.00"), _row(total_price="50.00")])
    summary = await backfill_platform_fees(db, _make_shop(), dry_run=True)

    assert not _updates(db), "dry-run must issue no UPDATE"
    assert summary["dry_run"] is True
    assert summary["matched"] == 2
    assert summary["updated"] == 0
    # 8% of 100 + 8% of 50
    assert summary["fee_total_by_currency"]["USD"] == pytest.approx(12.00)


@pytest.mark.asyncio
async def test_real_run_updates_each_matched_order():
    db = _make_db([_row(), _row()])
    summary = await backfill_platform_fees(db, _make_shop(), dry_run=False)

    assert len(_updates(db)) == 2
    assert summary["updated"] == 2
    assert summary["dry_run"] is False


# ---------- impact reporting ----------


@pytest.mark.asyncio
async def test_splits_immediate_pnl_impact_from_pending():
    """SHIPPED/COMPLETED orders are already inside REVENUE_STATUSES, so their fees
    move the P&L the moment this runs. NEW ones only will, later — the operator
    needs those two numbers apart before committing."""
    db = _make_db([
        _row(total_price="100.00", status=OrderStatus.COMPLETED),
        _row(total_price="100.00", status=OrderStatus.SHIPPED),
        _row(total_price="100.00", status=OrderStatus.NEW),
    ])
    summary = await backfill_platform_fees(db, _make_shop(), dry_run=True)

    assert summary["matched"] == 3
    assert summary["affects_pnl_now"] == 2
    assert summary["pending"] == 1
    assert summary["fee_total_by_currency"]["USD"] == pytest.approx(24.00)
    assert summary["fee_total_pnl_now_by_currency"]["USD"] == pytest.approx(16.00)


@pytest.mark.asyncio
async def test_totals_are_reported_per_currency():
    db = _make_db([
        _row(total_price="100.00", currency="USD"),
        _row(total_price="200.00", currency="UAH"),
    ])
    summary = await backfill_platform_fees(db, _make_shop(), dry_run=True)

    assert summary["fee_total_by_currency"] == {
        "USD": pytest.approx(8.00),
        "UAH": pytest.approx(16.00),
    }


@pytest.mark.asyncio
async def test_fee_arithmetic_matches_the_sync_path():
    """The backfill must not re-implement the fee — same helper, same rounding,
    or re-priced history would disagree with orders priced at creation."""
    db = _make_db([_row(total_price="10.05")])
    shop = _make_shop(fee_percent=Decimal("6.50"))
    await backfill_platform_fees(db, shop, dry_run=False)

    # 10.05 * 6.5% = 0.65325 → 0.65, exactly as compute_platform_fee gives.
    assert "0.65" in _updates(db)[0]


@pytest.mark.asyncio
async def test_empty_match_returns_zeroed_summary():
    db = _make_db([])
    summary = await backfill_platform_fees(db, _make_shop(), dry_run=False)

    assert summary["matched"] == 0
    assert summary["updated"] == 0
    assert summary["fee_total_by_currency"] == {}
    assert not _updates(db)
