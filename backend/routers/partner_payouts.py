"""
OrderHub CRM — Partner Payouts Router (PART-1)

Per-shop partner settlements, payments, balances. OWNER + MANAGER only;
DESIGNER → 403 via the router-level dependency.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.shop import Shop
from models.user import Capability, User, UserRole
from routers.dependencies import (
    get_current_user,
    require_capability,
    require_role,
    require_shop_access,
)
from schemas.partner_payout import (
    PartnerBalancesResponse,
    PartnerNamesResponse,
    PartnerPaymentCreate,
    PartnerPaymentListResponse,
    PartnerPaymentResponse,
    PartnerPayoutPreviewRequest,
    PartnerPayoutPreviewResponse,
    PartnerSettlementCreate,
    PartnerSettlementListResponse,
    PartnerSettlementResponse,
    SettlementStaleness,
    SettlementStalenessResponse,
)
from services import partner_payout_service
from services.access_service import get_capabilities

router = APIRouter(
    prefix="/api/shops/{shop_id}/partner-payouts",
    tags=["partner-payouts"],
    # USER-ACCESS-1: role gate + per-shop grant (path shop_id was previously trusted).
    # USER-ACCESS-2: partner payouts are a money surface — also require view_finance.
    dependencies=[
        Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
        Depends(require_shop_access),
        Depends(require_capability(Capability.VIEW_FINANCE)),
    ],
)


def _settlement_to_response(
    settlement, paid_amount: Decimal
) -> PartnerSettlementResponse:
    return PartnerSettlementResponse(
        id=settlement.id,
        shop_id=settlement.shop_id,
        partner_id=settlement.partner_id,
        partner_name=settlement.partner_name,
        formula_type=settlement.formula_type.value,
        percent=settlement.percent,
        period_start=settlement.period_start,
        period_end=settlement.period_end,
        base_amount=settlement.base_amount,
        base_currency=settlement.base_currency,
        computed_amount=settlement.computed_amount,
        fx_rate_used=settlement.fx_rate_used,
        paid_amount=paid_amount,
        notes=settlement.notes,
        created_at=settlement.created_at,
        created_by_user_id=settlement.created_by_user_id,
    )


#: Base terms that are itemised COSTS. The PROFIT base subtracts these, so the
#: term table would otherwise hand a VIEW_FINANCE-without-VIEW_COSTS caller the
#: period's COGS, fees and overhead — exactly the figures the finance page
#: strips for the same caller (routers/finance.py:_strip_itemised_costs).
_COST_TERMS = frozenset({"cogs", "non_shipping_fees", "allocated_overhead"})


def _strip_cost_terms(
    resp: PartnerPayoutPreviewResponse,
) -> PartnerPayoutPreviewResponse:
    """Drop the itemised cost components from the preview's term table.

    `base_amount` and `computed_amount` stay: they are `money`, gated by
    view_finance, and total cost being inferable from base vs revenue terms is
    the same accepted consequence documented for net_profit on the finance page
    (USER-ACCESS-2 OQ-3a). What is hidden is the itemised breakdown.
    """
    return resp.model_copy(
        update={"terms": [t for t in resp.terms if t.name not in _COST_TERMS]}
    )


@router.post("/preview", response_model=PartnerPayoutPreviewResponse)
async def preview_settlement(
    shop_id: uuid.UUID,
    payload: PartnerPayoutPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PartnerPayoutPreviewResponse:
    # The shop is loaded here (not in the service) purely so the base-quality
    # panel can branch on platform without the service reaching for it.
    shop = (
        await db.execute(select(Shop).where(Shop.id == shop_id))
    ).scalar_one_or_none()
    resp = await partner_payout_service.preview_settlement(
        db, shop_id, payload, shop=shop
    )
    caps = await get_capabilities(db, current_user)
    if not caps.has(Capability.VIEW_COSTS):
        resp = _strip_cost_terms(resp)
    return resp


@router.post(
    "/settlements",
    response_model=PartnerSettlementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_settlement(
    shop_id: uuid.UUID,
    payload: PartnerSettlementCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PartnerSettlementResponse:
    settlement = await partner_payout_service.create_settlement(
        db, shop_id, current_user.id, payload
    )
    return _settlement_to_response(settlement, Decimal(0))


@router.get("/settlements", response_model=PartnerSettlementListResponse)
async def list_settlements(
    shop_id: uuid.UUID,
    partner_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> PartnerSettlementListResponse:
    items, total = await partner_payout_service.list_settlements(
        db, shop_id, partner_id, limit, offset
    )
    progress = await partner_payout_service.compute_settlement_payment_progress(
        db, [s.id for s in items]
    )
    return PartnerSettlementListResponse(
        items=[
            _settlement_to_response(s, progress.get(s.id, Decimal(0)))
            for s in items
        ],
        total=total,
    )


@router.get("/settlements/staleness", response_model=SettlementStalenessResponse)
async def check_staleness(
    shop_id: uuid.UUID,
    limit: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> SettlementStalenessResponse:
    """Recompute OPEN settlements and report any whose base has since moved.

    Deliberately NOT folded into GET /settlements: that is the hot list-render
    path and each check costs 2-3 aggregates. On-demand keeps the table fast and
    makes the recompute an explicit act. `limit` is applied server-side so the
    client cannot ask for an unbounded recompute.

    Read-only in the strictest sense — a settlement is immutable and this invents
    no update path. The remedy for a stale settlement is delete-and-recreate.
    """
    items, checked, truncated = await partner_payout_service.check_settlement_staleness(
        db, shop_id, limit
    )
    return SettlementStalenessResponse(
        items=[SettlementStaleness(**i) for i in items],
        checked_count=checked,
        truncated=truncated,
    )


@router.delete(
    "/settlements/{settlement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_settlement(
    shop_id: uuid.UUID,
    settlement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    await partner_payout_service.delete_settlement(db, shop_id, settlement_id)


@router.post(
    "/payments",
    response_model=PartnerPaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment(
    shop_id: uuid.UUID,
    payload: PartnerPaymentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PartnerPaymentResponse:
    payment = await partner_payout_service.create_payment(
        db, shop_id, current_user.id, payload
    )
    return PartnerPaymentResponse.model_validate(payment)


@router.get("/payments", response_model=PartnerPaymentListResponse)
async def list_payments(
    shop_id: uuid.UUID,
    partner_id: uuid.UUID | None = Query(None),
    settlement_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> PartnerPaymentListResponse:
    items, total = await partner_payout_service.list_payments(
        db, shop_id, partner_id, settlement_id, limit, offset
    )
    return PartnerPaymentListResponse(
        items=[PartnerPaymentResponse.model_validate(p) for p in items],
        total=total,
    )


@router.delete(
    "/payments/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_payment(
    shop_id: uuid.UUID,
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    await partner_payout_service.delete_payment(db, shop_id, payment_id)


@router.get("/balances", response_model=PartnerBalancesResponse)
async def get_balances(
    shop_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PartnerBalancesResponse:
    items = await partner_payout_service.get_partner_balances(db, shop_id)
    return PartnerBalancesResponse(items=items)


@router.get("/partner-names", response_model=PartnerNamesResponse)
async def get_partner_names(
    shop_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PartnerNamesResponse:
    items = await partner_payout_service.list_partner_names(db, shop_id)
    return PartnerNamesResponse(items=items)
