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

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User, UserRole
from models.wb_parcel import WbParcel
from models.wb_tracking import WbParcelTracking, WbTrackingEvent
from routers.dependencies import require_role
from schemas.common import PaginatedResponse
from schemas.wb_parcel import WbParcelResponse
from schemas.wb_tracking import (
    TrackedParcelResponse,
    TrackingEventResponse,
    TrackingOverviewResponse,
    TrackingRefreshResponse,
)
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
            "Filter to one state, or a comma-separated set of them: "
            "delivered, moving, problem, no_data, untracked"
        ),
    ),
    limit: int | None = Query(None, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Delivery status of every WB parcel inside the tracking window (WB-TRACK-1).

    The classification is computed once, in `wb_tracking_service.classify_parcels`,
    and this route only filters and serialises it. The MCP tool and the
    WB-TRACK-2 page both read this endpoint precisely so there is one definition
    of "stuck" rather than two that drift apart.

    `counts` always describes the FULL set, not the filtered slice — a filtered
    view must not make the other states look empty. WB-TRACK-2 leans on that
    directly: its collapsed group headers show a count for rows it did not fetch.

    `state` accepts a comma-separated SET so the page can ask for everything
    except `delivered` in one call. A single value behaves exactly as before,
    which is what `mcp_server/tools_read.py:check_parcel_delivery` still sends.

    `limit` / `offset` page the FILTERED slice and default to off, so an
    unpaginated caller sees the payload it has always seen. They exist for the
    delivered group, which accumulates for the whole 60-day tracking window.
    """
    overview = await wb_tracking_service.classify_parcels(db)
    parcels = overview.parcels
    if state:
        wanted = {s.strip() for s in state.split(",") if s.strip()}
        parcels = [p for p in parcels if p.state in wanted]

    if limit is not None:
        parcels = parcels[offset : offset + limit]
    elif offset:
        parcels = parcels[offset:]

    return TrackingOverviewResponse(
        counts=overview.counts,
        parcels=[TrackedParcelResponse.model_validate(p) for p in parcels],
        polled_at=overview.polled_at,
        stalled_days=overview.stalled_days,
    )


@router.get(
    "/tracking/{tracking_number}/events",
    response_model=list[TrackingEventResponse],
)
async def get_tracking_events(
    tracking_number: str,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """The observed transition log for one parcel (WB-TRACK-2).

    Oldest first — the question this answers is "how did it get here", which
    reads forwards. `wb_tracking_event` holds one row per observed CHANGE, so a
    parcel polled daily without moving still has exactly one row; that is the
    signal, not a gap.

    Lazy and per-parcel on purpose: only the row an operator expands needs its
    history, and inlining every parcel's log on `/tracking` would grow that
    payload without bound.
    """
    exists = (
        await db.execute(
            select(WbParcelTracking.tracking_number).where(
                WbParcelTracking.tracking_number == tracking_number
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No tracking record for {tracking_number}",
        )

    rows = (
        (
            await db.execute(
                select(WbTrackingEvent)
                .where(WbTrackingEvent.tracking_number == tracking_number)
                .order_by(WbTrackingEvent.observed_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [TrackingEventResponse.model_validate(row) for row in rows]


@router.post("/tracking/refresh", response_model=TrackingRefreshResponse)
async def refresh_tracking(
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Force a tracking poll now instead of waiting for the daily job (WB-TRACK-2).

    Calls `wb_tracking_service.run_poll` — the EXACT function the scheduler's
    fifth job calls, not a parallel path. Still one keyless Nova Poshta request
    for the whole in-flight set.

    Throttled SERVER-side: a disabled button is a hint, and this route is
    reachable by anyone who can open the page. The cooldown is checked against
    the freshness signal itself (`max(last_polled_at)`), so it needs no stored
    state and correctly also absorbs a click made moments after the daily job
    ran — in both cases the honest answer is "this data is already current".
    """
    last_polled_at = await wb_tracking_service.load_last_polled_at(db)
    if last_polled_at is not None:
        cooldown = timedelta(
            minutes=wb_tracking_service.MANUAL_POLL_COOLDOWN_MINUTES
        )
        elapsed = datetime.now(timezone.utc) - last_polled_at
        if elapsed < cooldown:
            wait_seconds = int((cooldown - elapsed).total_seconds())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Tracking was refreshed less than "
                    f"{wb_tracking_service.MANUAL_POLL_COOLDOWN_MINUTES} minutes "
                    f"ago. Try again in {wait_seconds}s."
                ),
                headers={"Retry-After": str(wait_seconds)},
            )

    summary = await wb_tracking_service.run_poll(db)
    return TrackingRefreshResponse(
        **summary,
        polled_at=await wb_tracking_service.load_last_polled_at(db),
    )
