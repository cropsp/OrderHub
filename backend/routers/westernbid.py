"""
OrderHub CRM — WesternBid Router (WB-1, WB-TRACK-1)

Read-only admin views of the `wb_parcel` mirror and its Nova Poshta delivery
tracking. No mutations, no WB writes.

Access: OWNER + MANAGER via `require_role`, matching the global materials /
overhead catalogs (which are role-gated, not shop-scoped) — `wb_parcel` has no
`shop_id`, so the USER-ACCESS shop-scope machinery does not apply. It is NOT
`view_costs`-gated: this surface exposes only recipient / raw status text, no
itemised cost, so it stays off the money-visibility surface.

WB-TRACK-1 keeps both verdicts for `/tracking`, and neither is a copy-paste:
  * Unscoped is still right — WesternBid is ONE account across all shops (WB-1
    put its credentials in `app_settings`, not on `Shop`), so there is no shop to
    scope a parcel to. Neither route carries `{shop_id}`, which is why they do
    not appear in tests/test_route_scope_completeness.py; coverage is behavioural
    (DESIGNER 403 / MANAGER 200) in tests/test_wb_tracking.py.
  * Not money-gated is still right — and tracking carries LESS identity than the
    parcel list above: Nova Poshta's keyless endpoint masks `RecipientFullName`
    and `RecipientAddress`, so a destination city is all it returns.
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
from schemas.wb_tracking import TrackedParcelResponse, TrackingOverviewResponse
from services import wb_tracking_service

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


@router.get("/tracking", response_model=TrackingOverviewResponse)
async def get_tracking_overview(
    state: str | None = Query(
        None,
        description=(
            "Filter to one state: delivered, moving, problem, no_data, untracked"
        ),
    ),
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Delivery status of every WB parcel inside the tracking window (WB-TRACK-1).

    The classification is computed once, in `wb_tracking_service.classify_parcels`,
    and this route only filters and serialises it. The MCP tool and the future
    WB-TRACK-2 page both read this endpoint precisely so there is one definition
    of "stuck" rather than two that drift apart.

    `counts` always describes the FULL set, not the filtered slice — a filtered
    view must not make the other states look empty.
    """
    overview = await wb_tracking_service.classify_parcels(db)
    parcels = overview.parcels
    if state:
        parcels = [p for p in parcels if p.state == state]

    return TrackingOverviewResponse(
        counts=overview.counts,
        parcels=[TrackedParcelResponse.model_validate(p) for p in parcels],
        polled_at=overview.polled_at,
        stalled_days=overview.stalled_days,
    )
