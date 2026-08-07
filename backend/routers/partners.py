"""
OrderHub CRM — Partners Router (PARTNER-CONFIG-1)

Partner IDENTITY plus the cross-shop aggregate balance. OWNER-only throughout:
a partner determines money out, and the aggregate spans shops a scoped MANAGER
may not be able to see.

SCOPE-GUARD NOTE — read before adding a route here. These paths carry no
`{shop_id}`, so `tests/test_route_scope_completeness.py` cannot see them (its
enumeration is purely path-based) and they cannot be added to its CLASSIFIED map
either — the stale-entry test would then fail. That invisibility is only safe
because this router is OWNER-only and carries identity, not per-shop data. Any
route that needs to be visible to a scoped user belongs under
`/api/shops/{shop_id}/partner-config` instead. The routes are listed in that
test's INDIRECT_SHOP_ROUTES for the record and covered behaviourally by
tests/test_shop_access.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.partner import Partner
from models.user import User, UserRole
from routers.dependencies import get_current_user, require_role
from schemas.partner import (
    PartnerCreate,
    PartnerListResponse,
    PartnerResponse,
    PartnerUpdate,
)
from schemas.partner_payout import PartnerBalancesResponse
from services import partner_payout_service

router = APIRouter(
    prefix="/api/partners",
    tags=["partners"],
    dependencies=[Depends(require_role(UserRole.OWNER))],
)


@router.get("", response_model=PartnerListResponse)
async def list_partners(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
) -> PartnerListResponse:
    stmt = select(Partner).order_by(Partner.name)
    if not include_inactive:
        stmt = stmt.where(Partner.is_active.is_(True))
    rows = (await db.execute(stmt)).scalars().all()
    return PartnerListResponse(
        items=[PartnerResponse.model_validate(p) for p in rows]
    )


@router.post("", response_model=PartnerResponse, status_code=status.HTTP_201_CREATED)
async def create_partner(
    payload: PartnerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PartnerResponse:
    partner = Partner(
        name=payload.name.strip(),
        notes=payload.notes,
        created_by_user_id=current_user.id,
    )
    db.add(partner)
    try:
        await db.commit()
    except IntegrityError:
        # uq_partners_name. Surfacing this as a 409 rather than letting it 500 is
        # the whole point of the constraint: one person, one identity, one balance.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A partner named '{payload.name.strip()}' already exists.",
        )
    await db.refresh(partner)
    return PartnerResponse.model_validate(partner)


@router.patch("/{partner_id}", response_model=PartnerResponse)
async def update_partner(
    partner_id: uuid.UUID,
    payload: PartnerUpdate,
    db: AsyncSession = Depends(get_db),
) -> PartnerResponse:
    """Rename / deactivate / annotate.

    A rename does NOT rewrite `partner_name` on existing settlements or payments:
    those are creation-time snapshots of what the row said when it was agreed,
    the same reason `percent` and `formula_type` are snapshotted. Balances key on
    `partner_id` and therefore follow the rename correctly.
    """
    partner = (
        await db.execute(select(Partner).where(Partner.id == partner_id))
    ).scalar_one_or_none()
    if partner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found"
        )
    if payload.name is not None:
        partner.name = payload.name.strip()
    if payload.is_active is not None:
        partner.is_active = payload.is_active
    if payload.notes is not None:
        partner.notes = payload.notes
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another partner already uses that name.",
        )
    await db.refresh(partner)
    return PartnerResponse.model_validate(partner)


@router.get("/balances", response_model=PartnerBalancesResponse)
async def get_aggregate_balances(
    db: AsyncSession = Depends(get_db),
) -> PartnerBalancesResponse:
    """Every partner's balance across ALL shops, per currency.

    OWNER-only by router dependency. The per-shop view lives at
    /api/shops/{shop_id}/partner-payouts/balances and is what a scoped MANAGER
    sees — see get_partner_balances for why a scoped aggregate is not offered.
    """
    items = await partner_payout_service.get_partner_balances(db, shop_id=None)
    return PartnerBalancesResponse(items=items)
