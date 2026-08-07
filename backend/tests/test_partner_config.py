"""PARTNER-CONFIG-1 — new-base, FX-fold, overlap-guard and staleness guards.

Mock-based, same house style as test_partner_payout_service.py: mocked
AsyncSession, captured SQL compiled to strings, direct service invocations.

What each block pins:
  1. The FX fold — same-currency passthrough, UAH→USD division, one rate stamped,
     NULL rate when nothing converted, and the two distinguishable 422s.
  2. The 422 fires on the PRESENCE of an unconvertible term, not on its size.
  3. Term composition — TURNOVER and PROFIT subtract what they are supposed to,
     including the funded discount and refunds (PARTNER-REFUND-BASE).
  4. The overlap guard — straddle blocks, adjacent does not, and the predicate is
     scoped to one (shop, partner).
  5. Staleness — replays with the STORED rate and never resolves the current one;
     paid settlements are skipped.
  6. Legacy formulas still dispatch and still mean what they meant.
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
from services import partner_payout_service
from services.finance_service import compute_profit_terms, compute_turnover_terms
from services.fx_service import FxRates

RATE = Decimal("41.50")


def _compiled(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).lower()


def _make_db(execute_results=None):
    captured: list = []
    results = list(execute_results or [])

    async def fake_execute(stmt):
        captured.append(stmt)
        if results:
            return results.pop(0)
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


def _usd_ctx(fx=None):
    return partner_payout_service.BaseContext(
        settlement_currency="USD", fx=fx if fx is not None else FxRates.fixed(RATE)
    )


# ─── 1. The FX fold ────────────────────────────────────────────────────


def test_fold_passes_through_same_currency_and_stamps_no_rate():
    """NULL fx_rate_used means NO CONVERSION WAS APPLIED, never "rate unknown"."""
    terms = [("items_revenue", "USD", Decimal("100")), ("refunds", "USD", Decimal("-10"))]
    total, rate, detail = partner_payout_service._fold_to_currency(terms, _usd_ctx())
    assert total == Decimal("90")
    assert rate is None
    assert [t.converted for t in detail] == [Decimal("100"), Decimal("-10")]


def test_fold_converts_uah_overhead_into_usd_by_division():
    """The real Lamamarka case: USD orders, UAH overhead, USD settlement.

    UAH→USD is DIVISION (fx_service module docstring). Multiplying instead would
    inflate a warehouse cost ~1700x and still look plausible in a P&L.
    """
    terms = [
        ("items_revenue", "USD", Decimal("1000")),
        ("allocated_overhead", "UAH", Decimal("-4150")),
    ]
    total, rate, detail = partner_payout_service._fold_to_currency(terms, _usd_ctx())
    assert total == Decimal("900")  # 1000 - (4150 / 41.5)
    assert rate == RATE  # stamped onto the settlement, replayed by staleness
    overhead = next(t for t in detail if t.name == "allocated_overhead")
    assert overhead.currency == "UAH"
    assert overhead.amount == Decimal("-4150")  # source amount preserved
    assert overhead.converted == Decimal("-100")


def test_fold_422s_when_no_rate_is_configured():
    ctx = _usd_ctx(fx=FxRates.unavailable())
    with pytest.raises(HTTPException) as exc:
        partner_payout_service._fold_to_currency(
            [("allocated_overhead", "UAH", Decimal("-4150"))], ctx
        )
    assert exc.value.status_code == 422
    assert "no usable uah/usd rate" in exc.value.detail.lower()


def test_fold_422s_on_an_unsupported_pair_rather_than_dropping_the_term():
    """Rule 4: never silently drop a term, never leave a spurious base row."""
    with pytest.raises(HTTPException) as exc:
        partner_payout_service._fold_to_currency(
            [("items_revenue", "EUR", Decimal("500"))], _usd_ctx()
        )
    assert exc.value.status_code == 422
    assert "only uah↔usd" in exc.value.detail.lower()


def test_fold_422s_on_a_zero_amount_foreign_term():
    """The guard fires on the PRESENCE of a foreign bucket, not its magnitude.

    A bucket exists only because rows exist. Making the check amount-dependent
    would also make it rounding-dependent — a period with EUR orders that happen
    to net to 0.00 would settle silently, and the next one would not.
    """
    with pytest.raises(HTTPException) as exc:
        partner_payout_service._fold_to_currency(
            [("items_revenue", "EUR", Decimal("0"))], _usd_ctx()
        )
    assert exc.value.status_code == 422


def test_fold_returns_unrounded_total_for_a_single_late_quantize():
    """fx_service.convert returns unrounded on purpose; the fold must not round
    per term or the cents drift with the number of terms."""
    terms = [("allocated_overhead", "UAH", Decimal("-100"))]
    total, _rate, _detail = partner_payout_service._fold_to_currency(terms, _usd_ctx())
    assert total != total.quantize(Decimal("0.01"))  # still carrying full precision


# ─── 2. Term composition ───────────────────────────────────────────────


def _aggregate_results(*, discount=Decimal("0"), refunds=None, overhead=None):
    items_row = MagicMock()
    items_row.currency = "USD"
    items_row.items_revenue = Decimal("1000")
    items_row.cogs = Decimal("300")
    items_row.non_shipping_fees = Decimal("75")
    items_row.discount_total = discount
    items_result = MagicMock()
    items_result.all.return_value = [items_row]
    out = [items_result]

    if overhead is not None:
        o_row = MagicMock()
        o_row.currency = "UAH"
        o_row.allocated_overhead = overhead
        o_result = MagicMock()
        o_result.all.return_value = [o_row]
        out.append(o_result)

    r_result = MagicMock()
    if refunds is not None:
        r_row = MagicMock()
        r_row.currency = "USD"
        r_row.refunds = refunds
        r_result.all.return_value = [r_row]
    else:
        r_result.all.return_value = []
    out.append(r_result)
    return out


@pytest.mark.asyncio
async def test_turnover_subtracts_refunds_and_discount():
    """PARTNER-REFUND-BASE: both legacy bases paid the partner on refunded
    revenue. The new bases deduct the refund in the period it landed."""
    db, _ = _make_db(_aggregate_results(discount=Decimal("50"), refunds=Decimal("120")))
    terms = await compute_turnover_terms(
        db, uuid.uuid4(), date(2026, 5, 1), date(2026, 5, 31)
    )
    total, _rate, _detail = partner_payout_service._fold_to_currency(terms, _usd_ctx())
    assert total == Decimal("830")  # 1000 - 50 discount - 120 refunds
    assert {t[0] for t in terms} == {"items_revenue", "discount_total", "refunds"}
    # Turnover is gross of fees and COGS — that is what makes it turnover.
    assert "cogs" not in {t[0] for t in terms}
    assert "non_shipping_fees" not in {t[0] for t in terms}


@pytest.mark.asyncio
async def test_profit_subtracts_cogs_fees_overhead_refunds_and_discount():
    db, _ = _make_db(
        _aggregate_results(
            discount=Decimal("50"), refunds=Decimal("120"), overhead=Decimal("4150")
        )
    )
    terms = await compute_profit_terms(
        db, uuid.uuid4(), date(2026, 5, 1), date(2026, 5, 31)
    )
    total, rate, _detail = partner_payout_service._fold_to_currency(terms, _usd_ctx())
    # 1000 - 50 - 300 - 75 - (4150/41.5 = 100) - 120 = 355
    assert total == Decimal("355")
    assert rate == RATE


@pytest.mark.asyncio
async def test_profit_terms_are_exactly_the_five_non_shipping_components():
    """Rule 2: shipping revenue, shipping cost and anything shipping-adjacent
    stay out of every partner base. Asserted as an exact set rather than a
    substring scan, because `non_shipping_fees` is named for what it EXCLUDES —
    a naive "no term contains 'shipping'" check fails on the very term that
    proves the rule.

    `shipping_revenue`, `shipping_np_cost` and `shipping_discount` must never
    appear here. docs/design/profit-definition.md §6 is preserved, not reversed.
    """
    db, _ = _make_db(_aggregate_results(overhead=Decimal("100")))
    terms = await compute_profit_terms(
        db, uuid.uuid4(), date(2026, 5, 1), date(2026, 5, 31)
    )
    assert {name for name, _c, _a in terms} == {
        "items_revenue",
        "discount_total",
        "cogs",
        "non_shipping_fees",
        "allocated_overhead",
    }


# ─── 3. The overlap guard ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_overlap_query_is_scoped_to_one_shop_and_one_partner():
    """A settlement for a DIFFERENT partner on the same shop, or the same partner
    on a different shop, is not an overlap — several partners settle the same
    period independently."""
    db, captured = _make_db()
    await partner_payout_service.find_overlapping_settlements_for_partner(
        db, uuid.uuid4(), uuid.uuid4(), date(2026, 5, 1), date(2026, 5, 31)
    )
    sql = _compiled(captured[0])
    assert "partner_settlements.shop_id" in sql
    assert "partner_settlements.partner_id" in sql
    # Closed-interval overlap on both sides.
    assert "period_end >=" in sql
    assert "period_start <=" in sql


@pytest.mark.asyncio
async def test_create_settlement_blocks_an_overlapping_period():
    partner = MagicMock()
    partner.id = uuid.uuid4()
    partner.name = "Kseniia"
    existing = MagicMock()
    existing.period_start = date(2026, 5, 1)
    existing.period_end = date(2026, 5, 31)

    partner_result = MagicMock()
    partner_result.scalar_one_or_none.return_value = partner
    overlap_result = MagicMock()
    overlap_result.scalars.return_value.all.return_value = [existing]

    db, captured = _make_db([partner_result, overlap_result])
    from schemas.partner_payout import PartnerSettlementCreate

    payload = PartnerSettlementCreate(
        partner_id=partner.id,
        formula_type="turnover",
        percent=Decimal("10"),
        period_start=date(2026, 5, 15),  # straddles the existing period
        period_end=date(2026, 6, 15),
    )
    with pytest.raises(HTTPException) as exc:
        await partner_payout_service.create_settlement(
            db, uuid.uuid4(), uuid.uuid4(), payload
        )
    assert exc.value.status_code == 422
    assert "overlaps" in exc.value.detail.lower()
    assert "double-pay" in exc.value.detail.lower()
    # Cheap-first: the guard must reject BEFORE any aggregate runs. Two queries
    # only — the partner lookup and the overlap check.
    assert len(captured) == 2


def test_overlap_predicate_treats_a_touching_day_as_an_overlap():
    """[Jan 1 … Jan 31] and [Jan 31 … Feb 28] share Jan 31, which would be paid
    twice. The next period must start at last period_end + 1."""
    conds = partner_payout_service._overlap_predicate(date(2026, 1, 31), date(2026, 2, 28))
    assert len(conds) == 2
    # An unbounded upper edge yields only the lower-bound condition — the shape
    # the backfill diagnostic needs, and meaningless for a settlement period.
    assert len(partner_payout_service._overlap_predicate(date(2026, 1, 31), None)) == 1


# ─── 4. Staleness ──────────────────────────────────────────────────────


def _settlement(*, base=Decimal("100.00"), computed=Decimal("25.00"), rate=None):
    s = MagicMock()
    s.id = uuid.uuid4()
    s.period_start = date(2026, 5, 1)
    s.period_end = date(2026, 5, 31)
    s.base_amount = base
    s.base_currency = "USD"
    s.computed_amount = computed
    s.fx_rate_used = rate
    s.formula_type = PartnerSettlementFormula.TURNOVER
    return s


@pytest.mark.asyncio
async def test_staleness_replays_with_the_stored_rate_never_the_current_one(monkeypatch):
    """Rule 8. With the CURRENT rate every NBU move would flag every unpaid
    settlement and the badge would mean nothing."""
    settlement = _settlement(rate=Decimal("38.000000"))
    seen: list = []

    async def fake_base(db, shop_id, ps, pe, formula, *, ctx=None):
        seen.append(ctx)
        return partner_payout_service.BaseComputation(
            base_amount=Decimal("100.00"), base_currency="USD"
        )

    monkeypatch.setattr(partner_payout_service, "compute_base_amount", fake_base)
    resolve_spy = AsyncMock(side_effect=AssertionError("must not resolve current rate"))
    monkeypatch.setattr(partner_payout_service.fx_service, "resolve", resolve_spy)

    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [settlement]
    progress = MagicMock()
    progress.all.return_value = []  # no payments → open
    db, _ = _make_db([rows, progress])

    items, checked, truncated = await partner_payout_service.check_settlement_staleness(
        db, uuid.uuid4(), 25
    )
    assert checked == 1 and truncated is False
    assert items[0]["stale"] is False
    assert seen[0].fx.uah_per_usd == Decimal("38.000000")
    assert seen[0].fx.source == "pinned"
    resolve_spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_staleness_flags_a_moved_base(monkeypatch):
    """The load-bearing case: a refund lands dated inside an already-settled
    window, so the base moves under a settlement that cannot be edited."""
    settlement = _settlement(base=Decimal("100.00"))

    async def fake_base(db, shop_id, ps, pe, formula, *, ctx=None):
        return partner_payout_service.BaseComputation(
            base_amount=Decimal("88.00"), base_currency="USD"
        )

    monkeypatch.setattr(partner_payout_service, "compute_base_amount", fake_base)
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [settlement]
    progress = MagicMock()
    progress.all.return_value = []
    db, _ = _make_db([rows, progress])

    items, _checked, _truncated = await partner_payout_service.check_settlement_staleness(
        db, uuid.uuid4(), 25
    )
    assert items[0]["stale"] is True
    assert items[0]["recomputed_base_amount"] == Decimal("88.00")
    assert "100.00" in items[0]["reason"] and "88.00" in items[0]["reason"]


@pytest.mark.asyncio
async def test_staleness_never_recomputes_a_fully_paid_settlement(monkeypatch):
    """A paid settlement is closed history — money already left the business."""
    paid = _settlement(computed=Decimal("25.00"))

    async def fake_base(db, *a, **kw):
        raise AssertionError("a paid settlement must never be recomputed")

    monkeypatch.setattr(partner_payout_service, "compute_base_amount", fake_base)
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [paid]
    progress_row = MagicMock()
    progress_row.settlement_id = paid.id
    progress_row.paid_amount = Decimal("25.00")
    progress = MagicMock()
    progress.all.return_value = [progress_row]
    db, _ = _make_db([rows, progress])

    items, checked, _truncated = await partner_payout_service.check_settlement_staleness(
        db, uuid.uuid4(), 25
    )
    assert items == [] and checked == 0


@pytest.mark.asyncio
async def test_staleness_reports_rather_than_guesses_when_the_stored_rate_cannot_convert(
    monkeypatch,
):
    """A UAH term appeared in a window settled with fx_rate_used NULL. The delta
    genuinely cannot be computed at the frozen rate — say so, do not silently
    substitute today's rate."""
    settlement = _settlement(rate=None)

    async def fake_base(db, shop_id, ps, pe, formula, *, ctx=None):
        raise HTTPException(status_code=422, detail="no usable UAH/USD rate")

    monkeypatch.setattr(partner_payout_service, "compute_base_amount", fake_base)
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [settlement]
    progress = MagicMock()
    progress.all.return_value = []
    db, _ = _make_db([rows, progress])

    items, _c, _t = await partner_payout_service.check_settlement_staleness(
        db, uuid.uuid4(), 25
    )
    assert items[0]["stale"] is True
    assert items[0]["recomputed_base_amount"] is None
    assert "stored fx rate" in items[0]["reason"].lower()


@pytest.mark.asyncio
async def test_staleness_truncates_server_side(monkeypatch):
    async def fake_base(db, shop_id, ps, pe, formula, *, ctx=None):
        return partner_payout_service.BaseComputation(
            base_amount=Decimal("100.00"), base_currency="USD"
        )

    monkeypatch.setattr(partner_payout_service, "compute_base_amount", fake_base)
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [_settlement() for _ in range(5)]
    progress = MagicMock()
    progress.all.return_value = []
    db, _ = _make_db([rows, progress])

    items, checked, truncated = await partner_payout_service.check_settlement_staleness(
        db, uuid.uuid4(), 2
    )
    assert len(items) == 2 and checked == 2 and truncated is True


# ─── 5. Legacy formulas still dispatch ─────────────────────────────────


@pytest.mark.asyncio
async def test_all_four_formulas_dispatch():
    """Legacy values must keep deserialising forever — settlements are immutable
    historical facts (rule 2)."""
    assert set(partner_payout_service._FORMULA_DISPATCH) == set(
        PartnerSettlementFormula
    )


@pytest.mark.asyncio
async def test_legacy_formula_returns_per_currency_amounts_and_no_fx(monkeypatch):
    """The legacy path is untouched: no fold, no settlement currency, no rate."""
    async def fake_legacy(db, shop_id, ps, pe):
        return [CurrencyAmount(currency="UAH", amount=100.0)]

    monkeypatch.setitem(
        partner_payout_service._FORMULA_DISPATCH,
        PartnerSettlementFormula.REVENUE_ITEMS_MINUS_FEES,
        partner_payout_service._legacy(fake_legacy),
    )
    result = await partner_payout_service.compute_base_amount(
        MagicMock(),
        uuid.uuid4(),
        date(2026, 5, 1),
        date(2026, 5, 31),
        PartnerSettlementFormula.REVENUE_ITEMS_MINUS_FEES,
    )
    assert result.base_amount is None
    assert result.fx_rate_used is None
    assert result.amounts == [CurrencyAmount(currency="UAH", amount=100.0)]


def test_only_the_two_new_bases_are_selectable():
    """Rule 2 is enforced in Pydantic, not by a DB CHECK — PostgreSQL forbids a
    CHECK naming an enum value added in the same transaction."""
    from schemas.partner_payout import PartnerSettlementCreate

    for legacy in ("revenue_items_minus_fees", "net_profit_product_only"):
        with pytest.raises(Exception):
            PartnerSettlementCreate(
                partner_id=uuid.uuid4(),
                formula_type=legacy,
                percent=Decimal("10"),
                period_start=date(2026, 5, 1),
                period_end=date(2026, 5, 31),
            )


# ─── 6. Base-quality panel + cost censoring ────────────────────────────


@pytest.mark.asyncio
async def test_base_quality_counts_missing_cost_and_missing_platform_fee():
    """Rule 7 (a) + (c). Near-zero COGS coverage silently overstates a PROFIT
    base; a NULL platform_fee computes as fees = 0. Both become visible numbers
    instead of a silent overpay."""
    from models.shop import ShopPlatform
    from services.finance_service import compute_base_quality

    shop = MagicMock()
    shop.id = uuid.uuid4()
    shop.platform = ShopPlatform.SHOPIFY

    counts = MagicMock()
    counts.total_orders = 40
    counts.missing_cost = 37
    counts.missing_platform_fee = 12
    result = MagicMock()
    result.one.return_value = counts

    db, captured = _make_db([result])
    out = await compute_base_quality(db, shop, date(2026, 5, 1), date(2026, 5, 31))
    assert out["orders_missing_cost"] == 37
    assert out["orders_missing_platform_fee"] == 12
    assert out["etsy_refunds_unbooked"] is False
    # A Shopify shop must not pay for the Etsy statement query.
    assert len(captured) == 1
    assert out["etsy_months_without_statement"] == []


@pytest.mark.asyncio
async def test_base_quality_flags_unbooked_etsy_refunds():
    """Rule 7 (d): ETSY-REFUNDS is out of scope, so an Etsy shop's refund
    deduction is structurally zero. The panel reports it; it does not fix it."""
    from models.shop import ShopPlatform
    from services.finance_service import compute_base_quality

    shop = MagicMock()
    shop.id = uuid.uuid4()
    shop.platform = ShopPlatform.ETSY

    counts = MagicMock()
    counts.total_orders = 5
    counts.missing_cost = 5
    counts.missing_platform_fee = 0
    counts_result = MagicMock()
    counts_result.one.return_value = counts
    months_result = MagicMock()
    months_result.scalars.return_value.all.return_value = [date(2026, 1, 1)]

    db, captured = _make_db([counts_result, months_result])
    out = await compute_base_quality(db, shop, date(2026, 1, 1), date(2026, 1, 31))
    assert out["etsy_refunds_unbooked"] is True
    assert out["etsy_months_without_statement"] == ["2026-01-01"]
    assert len(captured) == 2


def test_preview_strips_itemised_cost_terms_without_view_costs():
    """USER-ACCESS-2: a VIEW_FINANCE-without-VIEW_COSTS caller sees the base and
    the revenue terms, but not the itemised cogs / fees / overhead — exactly what
    routers/finance.py:_strip_itemised_costs does for the finance page.

    Without this, the PROFIT preview's term table would hand that caller the
    period's COGS on a route gated only by view_finance.
    """
    from routers.partner_payouts import _strip_cost_terms
    from schemas.partner_payout import BaseTermDetail, PartnerPayoutPreviewResponse

    def term(name):
        return BaseTermDetail(
            name=name, currency="USD", amount=Decimal("1"), converted=Decimal("1")
        )

    resp = PartnerPayoutPreviewResponse(
        base_amount=Decimal("355.00"),
        base_currency="USD",
        computed_amount=Decimal("88.75"),
        terms=[
            term("items_revenue"),
            term("discount_total"),
            term("cogs"),
            term("non_shipping_fees"),
            term("allocated_overhead"),
            term("refunds"),
        ],
    )
    stripped = _strip_cost_terms(resp)
    assert {t.name for t in stripped.terms} == {
        "items_revenue",
        "discount_total",
        "refunds",
    }
    # The base itself is NOT hidden — it is `money`, gated by view_finance, and
    # cost being inferable from it is the accepted OQ-3a consequence.
    assert stripped.base_amount == Decimal("355.00")
    assert stripped.computed_amount == Decimal("88.75")
