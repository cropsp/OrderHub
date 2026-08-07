"""
OrderHub CRM — Partner Payout Service (PART-1, extended by PARTNER-CONFIG-1)

Computes partner settlement amounts, persists snapshots, tracks payments, and
exposes balances. Owns the CURRENCY FOLD and every 422 in the settlement flow —
`finance_service` deliberately never imports `fx_service`, so conversion policy
lives here, one layer up from the per-currency aggregates.

Critical invariants:
  - Settlements and payments are IMMUTABLE post-create. No update path.
  - Balance computation aggregates settlements and payments via TWO
    separate queries, then merges Python-side. A single LEFT JOIN would
    multiply rows when a partner has both N settlements and M payments.
  - Per-settlement payment progress is one GROUP BY query returning a
    dict for O(1) lookup during list rendering.
  - A PAID settlement is never recomputed. It is history.

PARTNER-CONFIG-1 notes worth keeping in view:
  - A whole period's foreign-currency terms convert at ONE spot rate, not a
    period average. Small for UAH overhead on a USD shop (the real case); not
    small if a UAH-revenue shop is ever settled in USD. Documented, not solved.
  - `OrderRefund.amount` may include a refunded-shipping portion, so subtracting
    it from a deliberately shipping-free base slightly over-deducts — in the
    business's favour, and accepted. Do not "fix" this without re-reading rule 3.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from models.partner import Partner
from models.partner_payment import PartnerPayment
from models.partner_settlement import PartnerSettlement, PartnerSettlementFormula
from schemas.finance import CurrencyAmount
from schemas.partner_payout import (
    PartnerBalance,
    PartnerPaymentCreate,
    PartnerPayoutPreviewRequest,
    PartnerPayoutPreviewResponse,
    PartnerSettlementCreate,
)
from services import fx_service
from services.finance_service import (
    compute_net_profit_product_only,
    compute_profit_terms,
    compute_revenue_items_minus_fees,
    compute_turnover_terms,
)
from services.fx_service import FxRates, normalize_currency

CENTS = Decimal("0.01")


@dataclass(frozen=True)
class BaseContext:
    """Everything a currency-folding base needs that the legacy bases do not.

    `settlement_currency=None` means "legacy per-currency behaviour" — no fold,
    no FX, one CurrencyAmount per currency, exactly as PART-1 did.
    """

    settlement_currency: str | None = None
    fx: FxRates = field(default_factory=FxRates.unavailable)


@dataclass(frozen=True)
class BaseTerm:
    """One component of a base, with its source and converted amounts."""

    name: str
    currency: str
    amount: Decimal  # unrounded, SOURCE currency
    converted: Decimal  # unrounded, SETTLEMENT currency


@dataclass(frozen=True)
class BaseComputation:
    """The result of computing a base, in both the legacy and the folded shape.

    `base_amount` is the EXACT unrounded Decimal and exists precisely so the new
    path never round-trips through `CurrencyAmount.amount`, which is a `float`
    (schemas/finance.py) consumed by the whole finance page and therefore not
    wideable. Legacy bases leave it None and populate `amounts` only.
    """

    amounts: list[CurrencyAmount] = field(default_factory=list)
    base_amount: Decimal | None = None
    base_currency: str | None = None
    fx_rate_used: Decimal | None = None
    terms: tuple[BaseTerm, ...] = ()


NEW_BASES = frozenset(
    {PartnerSettlementFormula.TURNOVER, PartnerSettlementFormula.PROFIT}
)

_TERM_BUILDERS = {
    PartnerSettlementFormula.TURNOVER: compute_turnover_terms,
    PartnerSettlementFormula.PROFIT: compute_profit_terms,
}


def _legacy(fn):
    """Adapt a PART-1 list-returning formula to the uniform BaseComputation shape.

    The two legacy formulas are left byte-identical: their SQL is pinned by
    tests/test_partner_payout_service.py and tests/test_finance_router.py, and an
    already-written settlement must keep meaning what it meant.
    """

    async def _run(db, shop_id, period_start, period_end, ctx: BaseContext):
        return BaseComputation(
            amounts=await fn(db, shop_id, period_start, period_end)
        )

    return _run


async def _run_folded_base(
    db: AsyncSession,
    shop_id: uuid.UUID,
    period_start: date,
    period_end: date,
    ctx: BaseContext,
    formula: PartnerSettlementFormula,
) -> BaseComputation:
    terms = await _TERM_BUILDERS[formula](db, shop_id, period_start, period_end)
    total, rate_used, detail = _fold_to_currency(terms, ctx)
    currency = normalize_currency(ctx.settlement_currency)
    return BaseComputation(
        # Exactly one row, always — including a genuinely zero base. The legacy
        # `if v != 0` drop-out (which then 422s as "no data") cannot happen here.
        amounts=[CurrencyAmount(currency=currency, amount=float(total))],
        base_amount=total,
        base_currency=currency,
        fx_rate_used=rate_used,
        terms=detail,
    )


def _fold_to_currency(
    terms, ctx: BaseContext
) -> tuple[Decimal, Decimal | None, tuple[BaseTerm, ...]]:
    """Fold signed per-currency terms into the settlement currency.

    Raises 422 on the PRESENCE of a term in a currency that cannot be converted,
    not on a non-zero amount: a currency bucket exists only because rows exist,
    and making the behaviour amount-dependent would also make it
    rounding-dependent. Rule 4 is explicit that a term is never silently dropped
    and a spurious separate-currency base row is never left behind.

    Returns the UNROUNDED total — the caller quantizes once.
    """
    target = normalize_currency(ctx.settlement_currency)
    total = Decimal(0)
    rate_used: Decimal | None = None
    detail: list[BaseTerm] = []

    for name, source_currency, amount in terms:
        source = normalize_currency(source_currency)
        if source == target:
            converted = amount
        else:
            if not ctx.fx.can_convert(frm=source, to=target):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=_fx_error_detail(name, source, target, ctx.fx),
                )
            converted = ctx.fx.convert(amount, frm=source, to=target)
            # Only UAH<->USD exists and `target` is one of them, so every
            # convertible foreign term is the other side — one rate suffices.
            rate_used = ctx.fx.rate_for(frm=source, to=target)
        total += converted
        detail.append(
            BaseTerm(
                name=name,
                currency=source,
                amount=amount,
                converted=converted,
            )
        )

    return total, rate_used, tuple(detail)


def _fx_error_detail(name: str, source: str, target: str, fx: FxRates) -> str:
    """Two distinguishable failures, because they need different fixes."""
    if {source, target} == {fx_service.BASE_CURRENCY, fx_service.QUOTE_CURRENCY}:
        return (
            f"This period has a {source} '{name}' term but no usable "
            f"{source}/{target} rate is configured. Set the rate in "
            "Settings → FX (or a manual override) and try again."
        )
    return (
        f"This period has a {source} '{name}' term and this partner settles in "
        f"{target}. Only UAH↔USD conversion is supported — split the period or "
        "reconcile the currency first."
    )


_FORMULA_DISPATCH = {
    PartnerSettlementFormula.REVENUE_ITEMS_MINUS_FEES: _legacy(
        compute_revenue_items_minus_fees
    ),
    PartnerSettlementFormula.NET_PROFIT_PRODUCT_ONLY: _legacy(
        compute_net_profit_product_only
    ),
    PartnerSettlementFormula.TURNOVER: lambda db, s, ps, pe, ctx: _run_folded_base(
        db, s, ps, pe, ctx, PartnerSettlementFormula.TURNOVER
    ),
    PartnerSettlementFormula.PROFIT: lambda db, s, ps, pe, ctx: _run_folded_base(
        db, s, ps, pe, ctx, PartnerSettlementFormula.PROFIT
    ),
}


async def compute_base_amount(
    db: AsyncSession,
    shop_id: uuid.UUID,
    period_start: date,
    period_end: date,
    formula_type: PartnerSettlementFormula,
    *,
    ctx: BaseContext | None = None,
) -> BaseComputation:
    """Dispatch to the right base composition.

    The NAME and the five POSITIONAL parameters are load-bearing: the service
    tests monkeypatch this module attribute positionally. New parameters are
    keyword-only for that reason.
    """
    return await _FORMULA_DISPATCH[formula_type](
        db, shop_id, period_start, period_end, ctx or BaseContext()
    )


# ─── Configuration resolution ──────────────────────────────


async def _resolve_context(
    db: AsyncSession,
    shop_id: uuid.UUID,
    partner_id: uuid.UUID | None,
    formula: PartnerSettlementFormula,
) -> BaseContext:
    """Build the fold context for a base, resolving FX exactly once.

    `fx_service.resolve()` is one indexed read over five settings keys and never
    fetches, so resolving eagerly costs ~nothing and buys the single injection
    point the staleness replay needs (it hands in a PINNED rate instead, and
    provably never touches `resolve`).
    """
    if formula not in NEW_BASES:
        return BaseContext()
    config = await _get_config(db, shop_id, partner_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This partner has no configuration on this shop. Add them in "
                "Shops → Edit Store Settings → Partners first."
            ),
        )
    return BaseContext(
        settlement_currency=config.settlement_currency,
        fx=await fx_service.resolve(db),
    )


async def _get_config(
    db: AsyncSession, shop_id: uuid.UUID, partner_id: uuid.UUID | None
):
    if partner_id is None:
        return None
    from models.shop_partner_config import ShopPartnerConfig

    stmt = select(ShopPartnerConfig).where(
        ShopPartnerConfig.shop_id == shop_id,
        ShopPartnerConfig.partner_id == partner_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


# ─── Overlap guard ─────────────────────────────────────────


def _overlap_predicate(period_start: date, period_end: date | None):
    """Closed-interval overlap: [a_start, a_end] ∩ [b_start, b_end] != ∅.

    Closed on both sides because the table's own CHECK is
    `period_end >= period_start` — a single-day period is legal, and two periods
    that merely touch on one day DO overlap and would double-pay that day.

    `period_end=None` means an unbounded upper edge, which is meaningful for a
    backfill window and meaningless for a settlement period; only
    `find_settlements_overlapping_period` passes it.
    """
    conditions = [PartnerSettlement.period_end >= period_start]
    if period_end is not None:
        conditions.append(PartnerSettlement.period_start <= period_end)
    return conditions


async def find_overlapping_settlements_for_partner(
    db: AsyncSession,
    shop_id: uuid.UUID,
    partner_id: uuid.UUID,
    period_start: date,
    period_end: date,
) -> list[PartnerSettlement]:
    """Existing settlements of the SAME (shop, partner) overlapping this period.

    Non-empty is a hard block on create (rule 5): with calculate-anytime cadence
    an overlapping settled period is a double payment, and settlements are
    immutable so it cannot be corrected in place. Delete-and-recreate is the only
    correction path.

    Sibling of `find_settlements_overlapping_period`, not a widening of it: that
    one is a read-only backfill DIAGNOSTIC returning JSON-ready dicts, takes an
    optional unbounded `until`, and deliberately has NO partner filter (a fee
    backfill moves every partner's future base). Folding both into one function
    would put two semantics behind one signature on a money surface. They share
    `_overlap_predicate` so the interval algebra exists exactly once.

    Served by ix_partner_settlements_shop_partner_period.
    """
    stmt = (
        select(PartnerSettlement)
        .where(
            PartnerSettlement.shop_id == shop_id,
            PartnerSettlement.partner_id == partner_id,
            *_overlap_predicate(period_start, period_end),
        )
        .order_by(PartnerSettlement.period_start)
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_last_period_end(
    db: AsyncSession, shop_id: uuid.UUID, partner_id: uuid.UUID | None
) -> date | None:
    """Latest settled period_end for this (shop, partner) — the UI defaults the
    next period_start to the day after it."""
    if partner_id is None:
        return None
    stmt = select(func.max(PartnerSettlement.period_end)).where(
        PartnerSettlement.shop_id == shop_id,
        PartnerSettlement.partner_id == partner_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


# ─── Preview / create ──────────────────────────────────────


async def preview_settlement(
    db: AsyncSession,
    shop_id: uuid.UUID,
    payload: PartnerPayoutPreviewRequest,
    shop=None,
) -> PartnerPayoutPreviewResponse:
    """Advisory. Never blocks — it REPORTS what would block.

    Rule 4 makes a missing FX rate a hard 422 on create; rule 7 makes the quality
    panel warnings-not-blocks. Those pull in opposite directions here, so preview
    catches the FX 422 and returns its message as `quality.fx_blocker`: the
    operator sees the warnings AND the reason Create is disabled in one round
    trip instead of a blank panel plus an error toast.
    """
    formula = PartnerSettlementFormula(payload.formula_type)
    overlapping = (
        await find_overlapping_settlements_for_partner(
            db, shop_id, payload.partner_id, payload.period_start, payload.period_end
        )
        if payload.partner_id is not None
        else []
    )
    last_period_end = await get_last_period_end(db, shop_id, payload.partner_id)

    quality = None
    if shop is not None:
        from services.finance_service import compute_base_quality

        quality_data = await compute_base_quality(
            db, shop, payload.period_start, payload.period_end
        )
        quality = _quality_panel(quality_data)

    fx_blocker: str | None = None
    result = BaseComputation()
    try:
        ctx = await _resolve_context(db, shop_id, payload.partner_id, formula)
        result = await compute_base_amount(
            db, shop_id, payload.period_start, payload.period_end, formula, ctx=ctx
        )
    except HTTPException as exc:
        if formula not in NEW_BASES:
            raise
        fx_blocker = str(exc.detail)

    if quality is not None:
        quality.fx_blocker = fx_blocker

    common = {
        "quality": quality,
        "overlapping": [
            {
                "id": s.id,
                "period_start": s.period_start,
                "period_end": s.period_end,
            }
            for s in overlapping
        ],
        "last_period_end": last_period_end,
    }

    if fx_blocker is not None:
        return PartnerPayoutPreviewResponse(**common)

    if result.base_amount is not None:
        base = result.base_amount.quantize(CENTS, rounding=ROUND_HALF_UP)
        return PartnerPayoutPreviewResponse(
            base_amount=base,
            base_currency=result.base_currency,
            computed_amount=(base * payload.percent / Decimal(100)).quantize(
                CENTS, rounding=ROUND_HALF_UP
            ),
            fx_rate_used=result.fx_rate_used,
            terms=[
                {
                    "name": t.name,
                    "currency": t.currency,
                    "amount": t.amount.quantize(CENTS, rounding=ROUND_HALF_UP),
                    "converted": t.converted.quantize(CENTS, rounding=ROUND_HALF_UP),
                }
                for t in result.terms
            ],
            **common,
        )

    # ── Legacy per-currency path, unchanged from PART-1 ──
    amounts = result.amounts
    if payload.currency:
        match = next((a for a in amounts if a.currency == payload.currency), None)
        base = Decimal(str(match.amount)) if match else Decimal(0)
        return PartnerPayoutPreviewResponse(
            base_amount=base.quantize(CENTS),
            base_currency=payload.currency,
            computed_amount=(base * payload.percent / Decimal(100)).quantize(CENTS),
            **common,
        )
    if len(amounts) == 1:
        only = amounts[0]
        base = Decimal(str(only.amount))
        return PartnerPayoutPreviewResponse(
            base_amount=base.quantize(CENTS),
            base_currency=only.currency,
            computed_amount=(base * payload.percent / Decimal(100)).quantize(CENTS),
            **common,
        )
    # Multi-currency without disambiguator → caller picks via `currency`.
    return PartnerPayoutPreviewResponse(available_currencies=amounts, **common)


def _quality_panel(data: dict):
    from schemas.partner_payout import BaseQualityPanel

    return BaseQualityPanel(**data)


async def create_settlement(
    db: AsyncSession,
    shop_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: PartnerSettlementCreate,
) -> PartnerSettlement:
    """Freeze a settlement. The base is always RECOMPUTED, never taken from a
    preview the client may have been holding for an hour.

    Order matters: the partner and the overlap guard are one indexed query each
    and the base is two or three aggregates, so a doomed request never pays for
    the aggregates it is about to be rejected for.
    """
    formula = PartnerSettlementFormula(payload.formula_type)

    partner = (
        await db.execute(select(Partner).where(Partner.id == payload.partner_id))
    ).scalar_one_or_none()
    if partner is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Partner not found.",
        )

    overlapping = await find_overlapping_settlements_for_partner(
        db, shop_id, payload.partner_id, payload.period_start, payload.period_end
    )
    if overlapping:
        periods = ", ".join(
            f"{s.period_start.isoformat()}…{s.period_end.isoformat()}"
            for s in overlapping
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"This period overlaps an existing settlement for {partner.name} "
                f"on this shop ({periods}). Overlapping periods double-pay the "
                "partner. Delete the existing settlement first, or start this "
                "one after its period_end."
            ),
        )

    ctx = await _resolve_context(db, shop_id, payload.partner_id, formula)
    result = await compute_base_amount(
        db, shop_id, payload.period_start, payload.period_end, formula, ctx=ctx
    )

    if result.base_amount is not None:
        # Folded path: exactly one currency, always — including a zero base.
        base = result.base_amount.quantize(CENTS, rounding=ROUND_HALF_UP)
        computed = (base * payload.percent / Decimal(100)).quantize(
            CENTS, rounding=ROUND_HALF_UP
        )
        settlement = PartnerSettlement(
            shop_id=shop_id,
            partner_id=partner.id,
            partner_name=partner.name,
            formula_type=formula,
            percent=payload.percent.quantize(CENTS),
            period_start=payload.period_start,
            period_end=payload.period_end,
            base_amount=base,
            base_currency=result.base_currency,
            computed_amount=computed,
            fx_rate_used=result.fx_rate_used,
            notes=payload.notes,
            created_by_user_id=user_id,
        )
        db.add(settlement)
        await db.commit()
        await db.refresh(settlement)
        return settlement

    return await _create_settlement_legacy(
        db, shop_id, user_id, payload, formula, partner, result.amounts
    )


async def _create_settlement_legacy(
    db: AsyncSession,
    shop_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: PartnerSettlementCreate,
    formula: PartnerSettlementFormula,
    partner: Partner,
    amounts: list[CurrencyAmount],
) -> PartnerSettlement:
    """PART-1 per-currency path, kept verbatim.

    Unreachable through the API today — `PartnerSettlementCreate.formula_type` is
    `SelectableBasisLiteral`, so a legacy formula cannot be requested. Kept
    because the dispatch still resolves legacy values (old rows must deserialise)
    and deleting the branch would make that dispatch half-defined.
    """
    payload_currency = getattr(payload, "currency", None)
    if payload_currency:
        match = next((a for a in amounts if a.currency == payload_currency), None)
        if match is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Formula produced no rows for currency '{payload_currency}'. "
                    f"Available: {[a.currency for a in amounts] or 'none'}"
                ),
            )
        base = Decimal(str(match.amount))
        currency = match.currency
    elif len(amounts) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Formula produced no data for the selected period.",
        )
    elif len(amounts) > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Period has multiple currencies; specify `currency` to pick one. "
                f"Available: {[a.currency for a in amounts]}"
            ),
        )
    else:
        base = Decimal(str(amounts[0].amount))
        currency = amounts[0].currency

    base = base.quantize(Decimal("0.01"))
    computed = (base * payload.percent / Decimal(100)).quantize(Decimal("0.01"))

    settlement = PartnerSettlement(
        shop_id=shop_id,
        partner_id=partner.id,
        partner_name=partner.name,
        formula_type=formula,
        percent=payload.percent.quantize(Decimal("0.01")),
        period_start=payload.period_start,
        period_end=payload.period_end,
        base_amount=base,
        base_currency=currency,
        computed_amount=computed,
        notes=payload.notes,
        created_by_user_id=user_id,
    )
    db.add(settlement)
    await db.commit()
    await db.refresh(settlement)
    return settlement


async def list_settlements(
    db: AsyncSession,
    shop_id: uuid.UUID,
    partner_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[PartnerSettlement], int]:
    """Filtered by partner_id, not by the `partner_name` snapshot.

    Filtering on the name would silently miss every settlement created before a
    rename — reintroducing exactly the split-balance bug the partner entity
    exists to prevent.
    """
    where = [PartnerSettlement.shop_id == shop_id]
    if partner_id is not None:
        where.append(PartnerSettlement.partner_id == partner_id)
    total_stmt = select(func.count()).select_from(PartnerSettlement).where(*where)
    total = (await db.execute(total_stmt)).scalar_one()
    rows_stmt = (
        select(PartnerSettlement)
        .where(*where)
        .order_by(PartnerSettlement.period_start.desc(), PartnerSettlement.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(rows_stmt)).scalars().all()
    return list(rows), int(total or 0)


async def delete_settlement(
    db: AsyncSession,
    shop_id: uuid.UUID,
    settlement_id: uuid.UUID,
) -> None:
    stmt = select(PartnerSettlement).where(
        PartnerSettlement.id == settlement_id,
        PartnerSettlement.shop_id == shop_id,
    )
    settlement = (await db.execute(stmt)).scalar_one_or_none()
    if settlement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settlement not found",
        )
    await db.delete(settlement)
    await db.commit()


async def create_payment(
    db: AsyncSession,
    shop_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: PartnerPaymentCreate,
) -> PartnerPayment:
    partner = (
        await db.execute(select(Partner).where(Partner.id == payload.partner_id))
    ).scalar_one_or_none()
    if partner is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Partner not found.",
        )
    if payload.settlement_id is not None:
        owning_stmt = select(PartnerSettlement).where(
            PartnerSettlement.id == payload.settlement_id,
            PartnerSettlement.shop_id == shop_id,
        )
        if (await db.execute(owning_stmt)).scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Linked settlement does not exist in this shop.",
            )
    payment = PartnerPayment(
        shop_id=shop_id,
        partner_id=partner.id,
        partner_name=partner.name,
        settlement_id=payload.settlement_id,
        amount=payload.amount.quantize(Decimal("0.01")),
        currency=payload.currency,
        paid_at=payload.paid_at,
        notes=payload.notes,
        created_by_user_id=user_id,
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


async def list_payments(
    db: AsyncSession,
    shop_id: uuid.UUID,
    partner_id: uuid.UUID | None,
    settlement_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[PartnerPayment], int]:
    """Filtered by partner_id — see list_settlements for why not by name."""
    where = [PartnerPayment.shop_id == shop_id]
    if partner_id is not None:
        where.append(PartnerPayment.partner_id == partner_id)
    if settlement_id is not None:
        where.append(PartnerPayment.settlement_id == settlement_id)
    total_stmt = select(func.count()).select_from(PartnerPayment).where(*where)
    total = (await db.execute(total_stmt)).scalar_one()
    rows_stmt = (
        select(PartnerPayment)
        .where(*where)
        .order_by(PartnerPayment.paid_at.desc(), PartnerPayment.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(rows_stmt)).scalars().all()
    return list(rows), int(total or 0)


async def delete_payment(
    db: AsyncSession,
    shop_id: uuid.UUID,
    payment_id: uuid.UUID,
) -> None:
    stmt = select(PartnerPayment).where(
        PartnerPayment.id == payment_id,
        PartnerPayment.shop_id == shop_id,
    )
    payment = (await db.execute(stmt)).scalar_one_or_none()
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )
    await db.delete(payment)
    await db.commit()


async def get_partner_balances(
    db: AsyncSession,
    shop_id: uuid.UUID | None = None,
) -> list[PartnerBalance]:
    """Per-(partner, currency) balance. One shop, or ALL shops when shop_id is None.

    Keyed on `partner_id`, not `partner_name`: identity is the whole point of the
    partners table, and keying on the snapshot string would resurrect the
    typo-splits-a-balance bug the moment a partner is renamed.

    The cross-shop form (shop_id=None) is OWNER-ONLY at the router. A MANAGER may
    hold `view_finance` on some shops and not others, so summing across shops for
    them would either leak money from shops they cannot see or return a partial
    total that looks authoritative. Neither is acceptable, so they get the
    per-shop form only.

    Aggregates settlements and payments via TWO SEPARATE queries, then merges
    Python-side. A single LEFT JOIN would multiply both sums when a partner has
    both N settlements and M payments.

    A partner settled in USD on one shop and UAH on another still yields two
    rows. There is deliberately no FX at the balance layer: what is owed in a
    currency is owed in that currency.
    """
    settled_stmt = (
        select(
            PartnerSettlement.partner_id,
            Partner.name.label("partner_name"),
            PartnerSettlement.base_currency.label("currency"),
            func.coalesce(func.sum(PartnerSettlement.computed_amount), 0).label(
                "total_settled"
            ),
        )
        .join(Partner, Partner.id == PartnerSettlement.partner_id)
        .group_by(
            PartnerSettlement.partner_id, Partner.name, PartnerSettlement.base_currency
        )
    )
    paid_stmt = (
        select(
            PartnerPayment.partner_id,
            Partner.name.label("partner_name"),
            PartnerPayment.currency,
            func.coalesce(func.sum(PartnerPayment.amount), 0).label("total_paid"),
        )
        .join(Partner, Partner.id == PartnerPayment.partner_id)
        .group_by(PartnerPayment.partner_id, Partner.name, PartnerPayment.currency)
    )
    if shop_id is not None:
        settled_stmt = settled_stmt.where(PartnerSettlement.shop_id == shop_id)
        paid_stmt = paid_stmt.where(PartnerPayment.shop_id == shop_id)

    settled_rows = (await db.execute(settled_stmt)).all()
    paid_rows = (await db.execute(paid_stmt)).all()

    combined: dict[tuple[uuid.UUID, str], dict] = {}
    for r in settled_rows:
        combined[(r.partner_id, r.currency)] = {
            "partner_name": r.partner_name,
            "total_settled": Decimal(r.total_settled),
            "total_paid": Decimal(0),
        }
    for r in paid_rows:
        key = (r.partner_id, r.currency)
        if key not in combined:
            combined[key] = {
                "partner_name": r.partner_name,
                "total_settled": Decimal(0),
                "total_paid": Decimal(0),
            }
        combined[key]["total_paid"] = Decimal(r.total_paid)

    return sorted(
        (
            PartnerBalance(
                partner_id=partner_id,
                partner_name=values["partner_name"],
                currency=currency,
                total_settled=values["total_settled"],
                total_paid=values["total_paid"],
                balance_owed=values["total_settled"] - values["total_paid"],
            )
            for (partner_id, currency), values in combined.items()
        ),
        key=lambda b: (b.partner_name, b.currency),
    )


async def compute_settlement_payment_progress(
    db: AsyncSession,
    settlement_ids: list[uuid.UUID],
) -> dict[uuid.UUID, Decimal]:
    """SUM(payments.amount) per settlement_id, returned as dict for O(1)
    lookup during list rendering.

    Only payments whose `currency` matches the parent settlement's
    `base_currency` contribute. A currency-mismatched payment (operator
    proceeded past the UI warning) is recorded but does NOT inflate this
    settlement's progress badge — it still counts in the partner's
    own-currency balance row.
    """
    if not settlement_ids:
        return {}
    stmt = (
        select(
            PartnerPayment.settlement_id,
            func.coalesce(func.sum(PartnerPayment.amount), 0).label("paid_amount"),
        )
        .join(
            PartnerSettlement,
            PartnerSettlement.id == PartnerPayment.settlement_id,
        )
        .where(PartnerPayment.settlement_id.in_(settlement_ids))
        .where(PartnerPayment.currency == PartnerSettlement.base_currency)
        .group_by(PartnerPayment.settlement_id)
    )
    rows = (await db.execute(stmt)).all()
    progress: dict[uuid.UUID, Decimal] = {sid: Decimal(0) for sid in settlement_ids}
    for r in rows:
        progress[r.settlement_id] = Decimal(r.paid_amount)
    return progress


async def find_settlements_overlapping_period(
    db: AsyncSession,
    shop_id: uuid.UUID,
    since: date,
    until: date | None,
) -> list[dict]:
    """SHOPIFY-BACKFILL Q4 pre-import diagnostic: existing (immutable) settlements
    whose [period_start, period_end] overlaps the backfill window [since, until].

    Importing historical orders does NOT alter these frozen snapshots, but it
    changes what a *future* settlement for the same period would compute — an
    already-settled period may now be under-settled. Surfaced in the dry-run so
    Sergii sees the affected periods before importing.
    """
    conditions = [
        PartnerSettlement.shop_id == shop_id,
        PartnerSettlement.period_end >= since,
    ]
    if until is not None:
        conditions.append(PartnerSettlement.period_start <= until)
    stmt = (
        select(PartnerSettlement)
        .where(*conditions)
        .order_by(PartnerSettlement.period_start.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(s.id),
            "partner_name": s.partner_name,
            "period_start": s.period_start.isoformat(),
            "period_end": s.period_end.isoformat(),
            "computed_amount": str(s.computed_amount),
            "base_currency": s.base_currency,
        }
        for s in rows
    ]


async def check_settlement_staleness(
    db: AsyncSession,
    shop_id: uuid.UUID,
    limit: int,
) -> tuple[list[dict], int, bool]:
    """Recompute OPEN settlements and flag any whose base has since moved.

    Why this exists (rule 8, promoted from PARTNER-SETTLEMENT-STALE): with
    calculate-anytime cadence, data that arrives AFTER a window was settled
    silently changes what that window's base would be. Refunds are dated into the
    period they land in — but a refund dated inside an ALREADY-settled window
    would otherwise escape deduction entirely. Etsy statements land monthly and
    Shopify refunds sync daily, so this is routine, not exotic.

    Three properties that make the badge mean something:

      - PAID settlements are never recomputed. They are closed history.
      - The replay uses the settlement's OWN stored `fx_rate_used`
        (`FxRates.fixed`), never the current rate — with the current rate every
        NBU move would flag every open settlement and the badge would be noise.
        This path provably never calls `fx_service.resolve()`.
      - Nothing is persisted. `partner_settlements` has no update path and this
        does not invent one; the remedy is delete-and-recreate.

    "Open" is `paid_amount < computed_amount`, which is wider than "no payment at
    all": a partially-paid settlement is still open money. A negative
    `computed_amount` (rule 6 — the partner owes back) makes that comparison
    incoherent, so those are always checkable.

    On-demand rather than on list render: `GET /settlements` is the hot path and
    this module's stated design goal is O(1) list rendering (see the header). Each
    check costs 2-3 aggregates, so `limit` is applied SERVER-side — the client
    cannot request an unbounded recompute.
    """
    stmt = (
        select(PartnerSettlement)
        .where(PartnerSettlement.shop_id == shop_id)
        .order_by(PartnerSettlement.period_start.desc())
    )
    settlements = list((await db.execute(stmt)).scalars().all())
    progress = await compute_settlement_payment_progress(
        db, [s.id for s in settlements]
    )
    open_settlements = [
        s
        for s in settlements
        if s.computed_amount < 0 or progress.get(s.id, Decimal(0)) < s.computed_amount
    ]
    truncated = len(open_settlements) > limit
    open_settlements = open_settlements[:limit]

    items: list[dict] = []
    for s in open_settlements:
        ctx = BaseContext(
            settlement_currency=s.base_currency,
            fx=FxRates.fixed(s.fx_rate_used),
        )
        try:
            result = await compute_base_amount(
                db, shop_id, s.period_start, s.period_end, s.formula_type, ctx=ctx
            )
        except HTTPException as exc:
            # A term that needs converting has appeared since this settlement was
            # frozen with no rate (or with one that no longer covers the pair).
            # That IS staleness, and the delta genuinely cannot be computed at
            # the frozen rate — say so rather than guessing at today's rate.
            items.append(
                {
                    "settlement_id": s.id,
                    "stale": True,
                    "recomputed_base_amount": None,
                    "reason": (
                        "A currency term appeared in this window that the "
                        f"settlement's stored FX rate cannot convert. {exc.detail}"
                    ),
                }
            )
            continue

        if result.base_amount is not None:
            recomputed = result.base_amount.quantize(CENTS, rounding=ROUND_HALF_UP)
        else:
            match = next(
                (a for a in result.amounts if a.currency == s.base_currency), None
            )
            recomputed = Decimal(str(match.amount if match else 0)).quantize(CENTS)

        stale = recomputed != s.base_amount
        items.append(
            {
                "settlement_id": s.id,
                "stale": stale,
                "recomputed_base_amount": recomputed,
                "reason": (
                    f"Base moved from {s.base_amount} to {recomputed} "
                    f"{s.base_currency} since this settlement was created."
                    if stale
                    else None
                ),
            }
        )

    return items, len(open_settlements), truncated


async def list_partner_names(
    db: AsyncSession,
    shop_id: uuid.UUID,
) -> list[str]:
    """DISTINCT union across both tables — autocomplete source."""
    settlements_q = (
        select(PartnerSettlement.partner_name.label("partner_name"))
        .where(PartnerSettlement.shop_id == shop_id)
        .distinct()
    )
    payments_q = (
        select(PartnerPayment.partner_name.label("partner_name"))
        .where(PartnerPayment.shop_id == shop_id)
        .distinct()
    )
    stmt = select(union_all(settlements_q, payments_q).subquery().c.partner_name).distinct()
    rows = (await db.execute(stmt)).scalars().all()
    return sorted({r for r in rows if r})
