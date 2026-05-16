"""PART-1 — partner_payout_service regression guards.

Mock-based, mirrors the test_consumption_service.py + test_overhead_materials_router.py
patterns: mocked AsyncSession, captured SQL compiled to strings, and direct
service-function invocations. No real DB.

Nine guards:
  1. revenue_items_minus_fees SQL joins order_items via subquery + filters by
     platform_fee (and NOT shipping_np_cost).
  2. net_profit_product_only SQL excludes shipping_np_cost AND subtracts
     overhead per currency.
  3. create_settlement persists snapshot values frozen from the formula.
  4. create_settlement with negative formula result still persists (loss-period
     policy: backend stores, UI warns).
  5. create_settlement raises 422 when formula returns no rows for the period.
  6. create_settlement raises 422 when multi-currency without disambiguator.
  7. get_partner_balances aggregates settlements + payments via two separate
     queries (NO single LEFT JOIN), and the resulting balance is correct on
     3-settlements × 2-payments fixture.
  8. compute_settlement_payment_progress short-circuits on empty input and
     returns Decimal(0) for settlements with no payments.
  9. delete_settlement raises 404 when not found in shop.
"""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from models.partner_settlement import PartnerSettlementFormula
from schemas.finance import CurrencyAmount
from schemas.partner_payout import (
    PartnerPaymentCreate,
    PartnerPayoutPreviewRequest,
    PartnerSettlementCreate,
)
from services import partner_payout_service
from services.finance_service import (
    _run_product_only_aggregate,
    compute_net_profit_product_only,
)


def _compiled(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()


def _make_db(execute_results=None):
    """captured = list of executed statements; results consumed in order."""
    captured: list = []
    results = list(execute_results or [])

    async def fake_execute(stmt):
        captured.append(stmt)
        if results:
            r = results.pop(0)
            return r
        r = MagicMock()
        r.all.return_value = []
        r.scalars.return_value.all.return_value = []
        r.scalar_one.return_value = 0
        r.scalar_one_or_none.return_value = None
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db, captured


# ─── 1. revenue_items_minus_fees SQL ────────────────────────────────────

@pytest.mark.asyncio
async def test_revenue_items_minus_fees_sql_excludes_shipping_cost():
    db, captured = _make_db()
    await _run_product_only_aggregate(
        db, uuid.uuid4(), date(2026, 5, 1), date(2026, 5, 31)
    )
    sql = _compiled(captured[-1])
    assert "order_items" in sql, f"must JOIN order_items: {sql}"
    assert "quantity * unit_price" in sql or "quantity * order_items.unit_price" in sql
    assert "platform_fee" in sql, f"must include platform_fee: {sql}"
    assert "shipping_np_cost" not in sql, (
        f"must EXCLUDE shipping_np_cost (partners don't share in shipping): {sql}"
    )


# ─── 2. net_profit_product_only orchestration ──────────────────────────

@pytest.mark.asyncio
async def test_net_profit_product_only_subtracts_overhead_per_currency():
    """Two execute calls: per-currency aggregate, then overhead aggregate."""
    items_row = MagicMock()
    items_row.currency = "UAH"
    items_row.items_revenue = 10000.0
    items_row.cogs = 3000.0
    items_row.non_shipping_fees = 500.0

    items_result = MagicMock()
    items_result.all.return_value = [items_row]

    overhead_row = MagicMock()
    overhead_row.currency = "UAH"
    overhead_row.allocated_overhead = 1500.0
    overhead_result = MagicMock()
    overhead_result.all.return_value = [overhead_row]

    db, _ = _make_db([items_result, overhead_result])
    result = await compute_net_profit_product_only(
        db, uuid.uuid4(), date(2026, 5, 1), date(2026, 5, 31)
    )
    assert len(result) == 1
    # 10000 - 3000 - 500 - 1500 = 5000
    assert result[0] == CurrencyAmount(currency="UAH", amount=5000.0)


# ─── 3. create_settlement snapshot freezing ────────────────────────────

@pytest.mark.asyncio
async def test_create_settlement_persists_snapshot(monkeypatch):
    async def fake_base(db, shop_id, ps, pe, formula):
        return [CurrencyAmount(currency="UAH", amount=9800.0)]

    monkeypatch.setattr(partner_payout_service, "compute_base_amount", fake_base)
    db, _ = _make_db()
    payload = PartnerSettlementCreate(
        partner_name="Олег",
        formula_type="net_profit_product_only",
        percent=Decimal("25"),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    user_id = uuid.uuid4()
    shop_id = uuid.uuid4()
    settlement = await partner_payout_service.create_settlement(
        db, shop_id, user_id, payload
    )
    assert settlement.base_amount == Decimal("9800.00")
    assert settlement.base_currency == "UAH"
    assert settlement.computed_amount == Decimal("2450.00")
    assert settlement.partner_name == "Олег"
    assert settlement.shop_id == shop_id
    assert settlement.created_by_user_id == user_id
    db.add.assert_called_once_with(settlement)
    db.commit.assert_awaited_once()


# ─── 4. negative-base settlement still saves ───────────────────────────

@pytest.mark.asyncio
async def test_create_settlement_with_negative_base_persists(monkeypatch):
    async def fake_base(db, shop_id, ps, pe, formula):
        return [CurrencyAmount(currency="UAH", amount=-500.0)]

    monkeypatch.setattr(partner_payout_service, "compute_base_amount", fake_base)
    db, _ = _make_db()
    payload = PartnerSettlementCreate(
        partner_name="Олег",
        formula_type="net_profit_product_only",
        percent=Decimal("10"),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    settlement = await partner_payout_service.create_settlement(
        db, uuid.uuid4(), uuid.uuid4(), payload
    )
    assert settlement.base_amount == Decimal("-500.00")
    assert settlement.computed_amount == Decimal("-50.00")


# ─── 5. empty-period 422 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_settlement_raises_422_when_formula_empty(monkeypatch):
    async def fake_base(db, shop_id, ps, pe, formula):
        return []

    monkeypatch.setattr(partner_payout_service, "compute_base_amount", fake_base)
    db, _ = _make_db()
    payload = PartnerSettlementCreate(
        partner_name="X",
        formula_type="revenue_items_minus_fees",
        percent=Decimal("25"),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    with pytest.raises(HTTPException) as exc:
        await partner_payout_service.create_settlement(
            db, uuid.uuid4(), uuid.uuid4(), payload
        )
    assert exc.value.status_code == 422


# ─── 6. multi-currency without disambiguator ───────────────────────────

@pytest.mark.asyncio
async def test_create_settlement_raises_422_on_multi_currency_no_filter(monkeypatch):
    async def fake_base(db, shop_id, ps, pe, formula):
        return [
            CurrencyAmount(currency="UAH", amount=10000.0),
            CurrencyAmount(currency="USD", amount=400.0),
        ]

    monkeypatch.setattr(partner_payout_service, "compute_base_amount", fake_base)
    db, _ = _make_db()
    payload = PartnerSettlementCreate(
        partner_name="X",
        formula_type="net_profit_product_only",
        percent=Decimal("10"),
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
    )
    with pytest.raises(HTTPException) as exc:
        await partner_payout_service.create_settlement(
            db, uuid.uuid4(), uuid.uuid4(), payload
        )
    assert exc.value.status_code == 422
    assert "multiple currencies" in exc.value.detail.lower()


# ─── 7. balances: NO row multiplication on N×M ─────────────────────────

@pytest.mark.asyncio
async def test_get_partner_balances_no_row_multiplication():
    """3 settlements + 2 payments for same partner+currency → balance is
    correct (sums of aggregates, not inflated by JOIN)."""
    # Aggregated rows (one per partner+currency, NOT raw rows)
    s_row = MagicMock()
    s_row.partner_name = "Олег"
    s_row.currency = "UAH"
    s_row.total_settled = Decimal("4500.00")  # 3 settlements: 1500+1500+1500
    settled_result = MagicMock()
    settled_result.all.return_value = [s_row]

    p_row = MagicMock()
    p_row.partner_name = "Олег"
    p_row.currency = "UAH"
    p_row.total_paid = Decimal("3000.00")  # 2 payments: 1500+1500
    paid_result = MagicMock()
    paid_result.all.return_value = [p_row]

    db, captured = _make_db([settled_result, paid_result])
    balances = await partner_payout_service.get_partner_balances(db, uuid.uuid4())

    assert len(balances) == 1
    assert balances[0].total_settled == Decimal("4500.00")
    assert balances[0].total_paid == Decimal("3000.00")
    assert balances[0].balance_owed == Decimal("1500.00")

    # Critical: two SEPARATE queries, neither containing a JOIN between
    # partner_settlements and partner_payments.
    assert len(captured) == 2
    sql1 = _compiled(captured[0])
    sql2 = _compiled(captured[1])
    assert "partner_settlements" in sql1 and "partner_payments" not in sql1
    assert "partner_payments" in sql2 and "partner_settlements" not in sql2


# ─── 8. per-settlement progress: empty input + zero default ─────────────

@pytest.mark.asyncio
async def test_compute_settlement_payment_progress_empty_and_default():
    db, captured = _make_db()
    out = await partner_payout_service.compute_settlement_payment_progress(db, [])
    assert out == {}
    assert captured == []  # no query

    sid1 = uuid.uuid4()
    sid2 = uuid.uuid4()
    row = MagicMock()
    row.settlement_id = sid1
    row.paid_amount = Decimal("700.00")
    result = MagicMock()
    result.all.return_value = [row]
    db, _ = _make_db([result])
    out = await partner_payout_service.compute_settlement_payment_progress(
        db, [sid1, sid2]
    )
    assert out[sid1] == Decimal("700.00")
    assert out[sid2] == Decimal("0")  # default for settlements with no payments


# ─── 9b. progress excludes currency-mismatched payments ────────────────

@pytest.mark.asyncio
async def test_compute_settlement_payment_progress_excludes_mismatched_currency():
    """Smoke-found bug: a UAH payment linked to a USD settlement inflated the
    badge to "Overpaid by 185.01 USD" because the SUM crossed currencies. The
    fix joins partner_settlements and filters
    PartnerPayment.currency = PartnerSettlement.base_currency. The mismatched
    payment still contributes to the partner's own-currency balance row."""
    usd_settlement_id = uuid.uuid4()
    sid_other = uuid.uuid4()

    # SQL-side: the JOIN+filter means only the 15 USD payment is returned.
    # (The 200 UAH payment is filtered out by the WHERE clause.)
    progress_row = MagicMock()
    progress_row.settlement_id = usd_settlement_id
    progress_row.paid_amount = Decimal("15.00")
    progress_result = MagicMock()
    progress_result.all.return_value = [progress_row]

    db, captured = _make_db([progress_result])
    progress = await partner_payout_service.compute_settlement_payment_progress(
        db, [usd_settlement_id, sid_other]
    )

    assert progress[usd_settlement_id] == Decimal("15.00")  # NOT 215 / overflow
    assert progress[sid_other] == Decimal("0")

    # SQL guard: the query must JOIN partner_settlements and filter on
    # PartnerPayment.currency = PartnerSettlement.base_currency.
    sql = _compiled(captured[0])
    assert "partner_settlements" in sql, (
        f"Query must JOIN partner_settlements to filter by base_currency. SQL: {sql}"
    )
    assert (
        "partner_payments.currency = partner_settlements.base_currency" in sql
    ), (
        "Query must filter payments to matching currency. "
        f"SQL: {sql}"
    )

    # And the per-(partner, currency) balance aggregate naturally keeps the
    # UAH payment in its own row (already covered by
    # test_get_partner_balances_no_row_multiplication — the aggregation is
    # GROUP BY currency, so the UAH payment surfaces as a UAH balance row
    # separate from the USD settlement balance row).
    s_row = MagicMock()
    s_row.partner_name = "Andriy"
    s_row.currency = "USD"
    s_row.total_settled = Decimal("29.99")
    settled_result = MagicMock()
    settled_result.all.return_value = [s_row]

    usd_paid = MagicMock()
    usd_paid.partner_name = "Andriy"
    usd_paid.currency = "USD"
    usd_paid.total_paid = Decimal("15.00")
    uah_paid = MagicMock()
    uah_paid.partner_name = "Andriy"
    uah_paid.currency = "UAH"
    uah_paid.total_paid = Decimal("200.00")
    paid_result = MagicMock()
    paid_result.all.return_value = [usd_paid, uah_paid]

    db, _ = _make_db([settled_result, paid_result])
    balances = await partner_payout_service.get_partner_balances(db, uuid.uuid4())
    balances_by_currency = {b.currency: b for b in balances}
    assert balances_by_currency["USD"].total_paid == Decimal("15.00")
    assert balances_by_currency["USD"].balance_owed == Decimal("14.99")
    # UAH balance row surfaces standalone — the mismatched payment is recorded
    # without contaminating the USD settlement progress.
    assert balances_by_currency["UAH"].total_settled == Decimal("0")
    assert balances_by_currency["UAH"].total_paid == Decimal("200.00")
    assert balances_by_currency["UAH"].balance_owed == Decimal("-200.00")


# ─── 9. delete_settlement 404 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_settlement_raises_404_when_not_in_shop():
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db, _ = _make_db([result])
    with pytest.raises(HTTPException) as exc:
        await partner_payout_service.delete_settlement(
            db, uuid.uuid4(), uuid.uuid4()
        )
    assert exc.value.status_code == 404
