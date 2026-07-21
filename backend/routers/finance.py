"""
OrderHub CRM — Finance Router (FIN-1)

Per-shop financial overview at /api/shops/{shop_id}/finance.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import Capability, User
from routers.dependencies import assert_capability, assert_shop_access, get_current_user
from schemas.finance import KpiCard, ShopFinanceResponse
from services.access_service import get_capabilities
from services.finance_service import get_shop_finance

router = APIRouter(prefix="/api/shops/{shop_id}/finance", tags=["finance"])


def _empty_kpi() -> KpiCard:
    return KpiCard(current=[], previous=[], change_percent=None)


def _strip_itemised_costs(resp: ShopFinanceResponse) -> ShopFinanceResponse:
    """Blank the itemised subtractive cards for a VIEW_FINANCE-without-VIEW_COSTS
    caller (USER-ACCESS-2, OQ-3 = a).

    Revenue and net_profit stay — net_profit is a margin figure gated by
    view_finance, and total cost being inferable from it (revenue − net_profit)
    is an accepted, documented consequence. What is hidden is the *itemised*
    breakdown: COGS, allocated overhead, fees, and shipping net. An empty
    `current` list makes the frontend auto-hide each card.
    """
    return resp.model_copy(
        update={
            "cogs": _empty_kpi(),
            "allocated_overhead_expenses": _empty_kpi(),
            "fees": _empty_kpi(),
            "shipping_net": _empty_kpi(),
        }
    )


@router.get("", response_model=ShopFinanceResponse)
async def get_shop_finance_overview(
    shop_id: uuid.UUID,
    start_date: date = Query(..., description="Inclusive start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Inclusive end date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShopFinanceResponse:
    # USER-ACCESS-1 (GAP A): shop scope still applies — a manager can only read
    # the finance of a shop they were granted.
    await assert_shop_access(db, shop_id, current_user)
    # USER-ACCESS-2: view_finance gates the P&L surface, replacing the old bare
    # require_role(OWNER, MANAGER). Composes with shop scope: a VF user still
    # cannot read a non-granted shop (asserted above).
    await assert_capability(db, Capability.VIEW_FINANCE, current_user)

    result = await get_shop_finance(db, shop_id, start_date, end_date)

    caps = await get_capabilities(db, current_user)
    if not caps.has(Capability.VIEW_COSTS):
        result = _strip_itemised_costs(result)
    return result
