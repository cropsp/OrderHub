"""
OrderHub CRM — Partner Payouts Router (PART-1)

Per-shop partner settlements, payments, balances. OWNER + MANAGER only;
DESIGNER → 403 via the router-level dependency.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User, UserRole
from routers.dependencies import get_current_user, require_role
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
)
from services import partner_payout_service

router = APIRouter(
    prefix="/api/shops/{shop_id}/partner-payouts",
    tags=["partner-payouts"],
    dependencies=[Depends(require_role(UserRole.OWNER, UserRole.MANAGER))],
)


def _settlement_to_response(
    settlement, paid_amount: Decimal
) -> PartnerSettlementResponse:
    return PartnerSettlementResponse(
        id=settlement.id,
        shop_id=settlement.shop_id,
        partner_name=settlement.partner_name,
        formula_type=settlement.formula_type.value,
        percent=settlement.percent,
        period_start=settlement.period_start,
        period_end=settlement.period_end,
        base_amount=settlement.base_amount,
        base_currency=settlement.base_currency,
        computed_amount=settlement.computed_amount,
        paid_amount=paid_amount,
        notes=settlement.notes,
        created_at=settlement.created_at,
        created_by_user_id=settlement.created_by_user_id,
    )


@router.post("/preview", response_model=PartnerPayoutPreviewResponse)
async def preview_settlement(
    shop_id: uuid.UUID,
    payload: PartnerPayoutPreviewRequest,
    db: AsyncSession = Depends(get_db),
) -> PartnerPayoutPreviewResponse:
    return await partner_payout_service.preview_settlement(db, shop_id, payload)


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
    partner: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> PartnerSettlementListResponse:
    items, total = await partner_payout_service.list_settlements(
        db, shop_id, partner, limit, offset
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
    partner: str | None = Query(None),
    settlement_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> PartnerPaymentListResponse:
    items, total = await partner_payout_service.list_payments(
        db, shop_id, partner, settlement_id, limit, offset
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
