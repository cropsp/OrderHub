"""
OrderHub CRM — Finance Router (FIN-1)

Per-shop financial overview at /api/shops/{shop_id}/finance.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User, UserRole
from routers.dependencies import assert_shop_access, require_role
from schemas.finance import ShopFinanceResponse
from services.finance_service import get_shop_finance

router = APIRouter(prefix="/api/shops/{shop_id}/finance", tags=["finance"])


@router.get("", response_model=ShopFinanceResponse)
async def get_shop_finance_overview(
    shop_id: uuid.UUID,
    start_date: date = Query(..., description="Inclusive start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Inclusive end date (YYYY-MM-DD)"),
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
) -> ShopFinanceResponse:
    # USER-ACCESS-1 (GAP A): a manager can only read the finance of a shop they
    # were granted — without this, any manager could read any shop's full P&L.
    await assert_shop_access(db, shop_id, current_user)
    return await get_shop_finance(db, shop_id, start_date, end_date)
