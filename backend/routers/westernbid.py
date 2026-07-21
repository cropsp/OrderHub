"""
OrderHub CRM — WesternBid Router (WB-1)

Read-only admin view of the `wb_parcel` mirror. No mutations, no WB writes.

Access: OWNER + MANAGER via `require_role`, matching the global materials /
overhead catalogs (which are role-gated, not shop-scoped) — `wb_parcel` has no
`shop_id`, so the USER-ACCESS shop-scope machinery does not apply. It is NOT
`view_costs`-gated: this surface exposes only recipient / raw status text, no
itemised cost, so it stays off the money-visibility surface.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User, UserRole
from models.wb_parcel import WbParcel
from routers.dependencies import require_role
from schemas.common import PaginatedResponse
from schemas.wb_parcel import WbParcelResponse

router = APIRouter(prefix="/api/westernbid", tags=["westernbid"])


@router.get("/parcels", response_model=PaginatedResponse[WbParcelResponse])
async def list_wb_parcels(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """List mirrored WesternBid parcels, newest first. Raw status fields, no
    actions (WB-1 is read-only)."""
    total = (
        await db.execute(select(func.count()).select_from(WbParcel))
    ).scalar_one()

    result = await db.execute(
        select(WbParcel)
        .order_by(WbParcel.last_seen_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    parcels = result.scalars().all()

    return PaginatedResponse[WbParcelResponse](
        items=[WbParcelResponse.model_validate(p) for p in parcels],
        total=total,
        page=page,
        limit=limit,
        pages=(total + limit - 1) // limit if limit else 0,
    )
