"""
OrderHub CRM — Partner Payout Service (PART-1)

Computes partner settlement amounts via the two formulas in
finance_service, persists snapshots, tracks payments, and exposes the
per-(shop, partner, currency) balance.

Critical invariants:
  - Settlements and payments are IMMUTABLE post-create. No update path.
  - Balance computation aggregates settlements and payments via TWO
    separate queries, then merges Python-side. A single LEFT JOIN would
    multiply rows when a partner has both N settlements and M payments.
  - Per-settlement payment progress is one GROUP BY query returning a
    dict for O(1) lookup during list rendering.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

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
from services.finance_service import (
    compute_net_profit_product_only,
    compute_revenue_items_minus_fees,
)


_FORMULA_DISPATCH = {
    PartnerSettlementFormula.REVENUE_ITEMS_MINUS_FEES: compute_revenue_items_minus_fees,
    PartnerSettlementFormula.NET_PROFIT_PRODUCT_ONLY: compute_net_profit_product_only,
}


async def compute_base_amount(
    db: AsyncSession,
    shop_id: uuid.UUID,
    period_start: date,
    period_end: date,
    formula_type: PartnerSettlementFormula,
) -> list[CurrencyAmount]:
    """Dispatch to the right finance_service helper."""
    return await _FORMULA_DISPATCH[formula_type](
        db, shop_id, period_start, period_end
    )


async def preview_settlement(
    db: AsyncSession,
    shop_id: uuid.UUID,
    payload: PartnerPayoutPreviewRequest,
) -> PartnerPayoutPreviewResponse:
    formula = PartnerSettlementFormula(payload.formula_type)
    amounts = await compute_base_amount(
        db, shop_id, payload.period_start, payload.period_end, formula
    )
    if payload.currency:
        match = next((a for a in amounts if a.currency == payload.currency), None)
        base = Decimal(str(match.amount)) if match else Decimal(0)
        return PartnerPayoutPreviewResponse(
            base_amount=base.quantize(Decimal("0.01")),
            base_currency=payload.currency,
            computed_amount=(base * payload.percent / Decimal(100)).quantize(
                Decimal("0.01")
            ),
        )
    if len(amounts) == 1:
        only = amounts[0]
        base = Decimal(str(only.amount))
        return PartnerPayoutPreviewResponse(
            base_amount=base.quantize(Decimal("0.01")),
            base_currency=only.currency,
            computed_amount=(base * payload.percent / Decimal(100)).quantize(
                Decimal("0.01")
            ),
        )
    # Multi-currency without disambiguator → caller picks via `currency`.
    return PartnerPayoutPreviewResponse(available_currencies=amounts)


async def create_settlement(
    db: AsyncSession,
    shop_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: PartnerSettlementCreate,
) -> PartnerSettlement:
    formula = PartnerSettlementFormula(payload.formula_type)
    amounts = await compute_base_amount(
        db, shop_id, payload.period_start, payload.period_end, formula
    )
    if payload.currency:
        match = next((a for a in amounts if a.currency == payload.currency), None)
        if match is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Formula produced no rows for currency '{payload.currency}'. "
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
        partner_name=payload.partner_name,
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
    partner: str | None,
    limit: int,
    offset: int,
) -> tuple[list[PartnerSettlement], int]:
    where = [PartnerSettlement.shop_id == shop_id]
    if partner:
        where.append(PartnerSettlement.partner_name == partner)
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
        partner_name=payload.partner_name,
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
    partner: str | None,
    settlement_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[PartnerPayment], int]:
    where = [PartnerPayment.shop_id == shop_id]
    if partner:
        where.append(PartnerPayment.partner_name == partner)
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
    shop_id: uuid.UUID,
) -> list[PartnerBalance]:
    """Per-(partner, currency) balance for one shop.

    Aggregates settlements and payments via TWO SEPARATE queries, then
    merges Python-side. A single LEFT JOIN would multiply both sums when
    a partner has both N settlements and M payments.
    """
    settled_stmt = (
        select(
            PartnerSettlement.partner_name,
            PartnerSettlement.base_currency.label("currency"),
            func.coalesce(func.sum(PartnerSettlement.computed_amount), 0).label(
                "total_settled"
            ),
        )
        .where(PartnerSettlement.shop_id == shop_id)
        .group_by(PartnerSettlement.partner_name, PartnerSettlement.base_currency)
    )
    paid_stmt = (
        select(
            PartnerPayment.partner_name,
            PartnerPayment.currency,
            func.coalesce(func.sum(PartnerPayment.amount), 0).label("total_paid"),
        )
        .where(PartnerPayment.shop_id == shop_id)
        .group_by(PartnerPayment.partner_name, PartnerPayment.currency)
    )
    settled_rows = (await db.execute(settled_stmt)).all()
    paid_rows = (await db.execute(paid_stmt)).all()

    combined: dict[tuple[str, str], dict[str, Decimal]] = {}
    for r in settled_rows:
        combined[(r.partner_name, r.currency)] = {
            "total_settled": Decimal(r.total_settled),
            "total_paid": Decimal(0),
        }
    for r in paid_rows:
        key = (r.partner_name, r.currency)
        if key not in combined:
            combined[key] = {
                "total_settled": Decimal(0),
                "total_paid": Decimal(0),
            }
        combined[key]["total_paid"] = Decimal(r.total_paid)

    return [
        PartnerBalance(
            partner_name=name,
            currency=currency,
            total_settled=values["total_settled"],
            total_paid=values["total_paid"],
            balance_owed=values["total_settled"] - values["total_paid"],
        )
        for (name, currency), values in sorted(combined.items())
    ]


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
