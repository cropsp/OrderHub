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

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User, UserRole
from models.wb_parcel import WbParcel
from models.wb_parcel_alert import WbParcelAlert
from models.wb_tracking import WbParcelTracking, WbTrackingEvent
from routers.dependencies import require_role
from schemas.common import PaginatedResponse
from schemas.wb_alert import ParcelAlertListResponse, ParcelAlertResponse
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
    parcel polled repeatedly without moving still has exactly one row; that is
    the signal, not a gap.

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
    """Force a tracking poll now instead of waiting for the 4-hourly job (WB-TRACK-2).

    Calls `wb_tracking_service.run_poll` — the EXACT function the scheduler's
    fifth job calls, not a parallel path. Still one keyless Nova Poshta request
    for the whole in-flight set.

    Throttled SERVER-side: a disabled button is a hint, and this route is
    reachable by anyone who can open the page. The cooldown is checked against
    the freshness signal itself (`max(last_polled_at)`), so it needs no stored
    state and correctly also absorbs a click made moments after the scheduled
    job ran — in both cases the honest answer is "this data is already current".
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


def _serialise_alert(
    alert: WbParcelAlert, parcel: WbParcel | None, now: datetime
) -> ParcelAlertResponse:
    """One alert row plus the display fields joined from the parcel mirror.

    `parcel` is never None in practice — the FK is `ON DELETE CASCADE` — but a
    monitoring surface degrading to a blank cell beats it 500-ing.
    """
    return ParcelAlertResponse(
        id=alert.id,
        kind=alert.kind,
        detail=alert.detail,
        shipment_id=alert.shipment_id,
        tracking_number=(
            wb_tracking_service.extract_novapost_number(parcel) if parcel else None
        ),
        tracking_numbers=(
            wb_tracking_service.carrier_tracking_numbers(parcel) if parcel else []
        ),
        recipient_name=parcel.recipient_name if parcel else None,
        carrier=parcel.shipping_type if parcel else None,
        raised_at=alert.raised_at,
        age_days=wb_tracking_service.alert_age_days(now, alert.raised_at),
        dismissed_at=alert.dismissed_at,
        dismissed_by_id=alert.dismissed_by_id,
    )


@router.get("/alerts", response_model=ParcelAlertListResponse)
async def list_parcel_alerts(
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Open, undismissed parcel alerts for the dashboard block (WB-ALERTS-1).

    A plain read — the alerts were computed during the poll, not here, so this
    endpoint never classifies and never writes. That matters: the dashboard
    calls it on every load for every OWNER/MANAGER.

    Same access stance as the rest of this router (`WB-TRACK-1` OQ6): parcels
    are global, not shop-scoped, and with three roles in the system
    OWNER+MANAGER is exactly "everyone who sees the dashboard, minus DESIGNER"
    (task rule 8).

    Ordering groups a parcel's alerts together, worst parcel first. Several
    kinds may be open on one parcel — task rule 3 dedupes per (parcel, kind) —
    so `59500007135457` can legitimately occupy two rows, and they should read
    as one block rather than being scattered across the list. Sorted in Python
    like `/tracking` does: this is a handful of rows, and the severity order
    lives in the service beside the kinds it ranks.
    """
    rows = (
        await db.execute(
            select(WbParcelAlert, WbParcel)
            .outerjoin(WbParcel, WbParcel.shipment_id == WbParcelAlert.shipment_id)
            .where(
                WbParcelAlert.resolved_at.is_(None),
                WbParcelAlert.dismissed_at.is_(None),
            )
        )
    ).all()

    now = datetime.now(timezone.utc)
    order = wb_tracking_service.ALERT_KIND_ORDER

    def kind_rank(kind: str) -> int:
        # An unknown kind sorts last rather than raising — the vocabulary can
        # grow without this route needing a deploy in lockstep.
        return order.index(kind) if kind in order else len(order)

    worst_per_parcel: dict[uuid.UUID, int] = {}
    for alert, _parcel in rows:
        rank = kind_rank(alert.kind)
        current = worst_per_parcel.get(alert.shipment_id)
        if current is None or rank < current:
            worst_per_parcel[alert.shipment_id] = rank

    ordered = sorted(
        rows,
        key=lambda pair: (
            worst_per_parcel[pair[0].shipment_id],
            str(pair[0].shipment_id),
            kind_rank(pair[0].kind),
        ),
    )

    return ParcelAlertListResponse(
        alerts=[_serialise_alert(alert, parcel, now) for alert, parcel in ordered],
        synced_at=await wb_tracking_service.load_last_polled_at(db),
    )


@router.post("/alerts/{alert_id}/dismiss", response_model=ParcelAlertResponse)
async def dismiss_parcel_alert(
    alert_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Mark one alert as handled, recording who and when (task rule 4).

    Same gate as `POST /tracking/refresh` — DESIGNER neither sees nor dismisses
    alerts.

    The row stays OPEN (`resolved_at` untouched). That is what stops the next
    poll from re-raising it while the condition persists, and it is also what
    lets the condition's eventual disappearance close it normally, so a later
    recurrence is a genuinely new episode (task rule 5).

    Dismissing an already-dismissed alert is a no-op rather than an error: a
    double-click must not rewrite who dismissed it or when.
    """
    alert = await db.get(WbParcelAlert, alert_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No parcel alert {alert_id}",
        )

    if alert.resolved_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"This alert closed itself already (resolution: "
                f"{alert.resolution}); there is nothing to dismiss."
            ),
        )

    now = datetime.now(timezone.utc)
    if alert.dismissed_at is None:
        alert.dismissed_at = now
        alert.dismissed_by_id = current_user.id

    parcel = await db.get(WbParcel, alert.shipment_id)
    return _serialise_alert(alert, parcel, now)
