"""
OrderHub CRM — Warehouse Router (WH-5)

One route: the one-off retro-consumption backfill. OWNER-only, dry-run by default,
and deliberately out of the MCP agent's reach — the agent authenticates as a
MANAGER, so the role gate is the whole story.

Never wire this into a scheduler, a sync hook or a startup task. It is a
human-initiated catch-up that exists because WH-2 is forward-only, and it is safe
exactly once: before the first partner settlement (runbook Phase 5).

SCOPE-GUARD NOTE — read before adding a route here. This path carries no
`{shop_id}`, so `tests/test_route_scope_completeness.py` cannot see it (its
enumeration is purely path-based) and it cannot be added to that test's CLASSIFIED
map either — the stale-entry test would then fail. The invisibility is only safe
because this router is OWNER-only, and OWNER is unrestricted by definition
(access_service short-circuits for it), so there is no shop scope left to enforce.
Any route here that must be reachable by a scoped user belongs under
`/api/shops/{shop_id}/...` instead. The route is listed in that test's
INDIRECT_SHOP_ROUTES for the record.

MONEY NOTE: the report carries per-order production costs, so unlike its sibling
backfills in routers/shops.py it returns a typed response_model rather than a bare
dict — that is what makes those fields visible to
tests/test_money_field_completeness.py, where they are classified `cost` against
this route's `view_costs-403` verdict.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User, UserRole
from routers.dependencies import get_current_user, require_role
from schemas.warehouse import (
    RETRO_ELIGIBLE_STATUSES,
    ConsumptionBackfillReport,
    ConsumptionBackfillRequest,
)
from services.consumption_backfill_service import run_consumption_backfill

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/warehouse",
    tags=["Warehouse"],
    dependencies=[Depends(require_role(UserRole.OWNER))],
)


@router.post("/backfill-consumption", response_model=ConsumptionBackfillReport)
async def backfill_consumption(
    body: ConsumptionBackfillRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConsumptionBackfillReport:
    """Consume BOM materials + the parcel's box for orders that already shipped.

    WH-2 moved packaging consumption onto the SHIPPED transition and books the
    box's cost into per-order COGS, but only forward — the ~7 months of orders
    already sitting in SHIPPED/COMPLETED have no movements and no cost snapshot.
    This walks them, resolves the box each one went out in (the operator's choice,
    else the calculator's suggestion, else the products' default box), persists it
    onto the order, and calls the SAME consumption service a live shipment calls.

    `dry_run=true` (the default) reports exactly what an execute would do and then
    discards the transaction. It is not an estimate: the same code runs against the
    same service, so the costs, the FX conversions and the negative-stock cascade
    in the report are the ones a real run would produce.

    Orders already consumed are skipped by the consumption service's own
    idempotency guard and reported as such, which makes re-runs and tranches safe.
    One order failing cannot abort the batch — it is isolated to its own SAVEPOINT
    and listed with its reason.

    OWNER-only, like the platform-fee backfill and for the same reason: this writes
    `computed_production_cost`, moves stock, and moves every future partner-payout
    base. The MCP agent is a MANAGER and cannot reach it.
    """
    statuses = list(body.statuses or RETRO_ELIGIBLE_STATUSES)

    try:
        report = await run_consumption_backfill(
            db,
            user=current_user,
            statuses=statuses,
            dry_run=body.dry_run,
            limit=body.limit,
            shop_id=body.shop_id,
        )
        # The service already rolled back on a dry run. Repeating it here is the
        # fee-backfill's belt-and-suspenders: two independent guards, because the
        # cost of a dry run that silently wrote is a warehouse nobody can trust.
        if body.dry_run:
            await db.rollback()
    except Exception as e:
        logger.error(f"[WAREHOUSE] Retro consumption backfill failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Retro consumption backfill failed: {str(e)}",
        )

    # A real run commits via get_db on return, like every other backfill.
    return report
