"""
OrderHub CRM — Dashboard Router
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User, UserRole
from models.order import Order, OrderStatus
from schemas.dashboard import DashboardResponse, DashboardStats, RevenueByCurrency
from routers.dependencies import get_current_user, require_role

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard statistics and revenue (revenue only shown to owners)."""
    
    # 1. Orders by Status
    # Base query for all active orders
    status_query = select(Order.status, func.count()).group_by(Order.status)
    
    # Designer only sees their assigned orders stats
    if current_user.role == UserRole.DESIGNER:
        status_query = status_query.where(Order.assigned_designer_id == current_user.id)
        
    status_result = await db.execute(status_query)
    orders_by_status = {status.value: count for status, count in status_result.all()}
    
    # Total active orders
    total_orders = sum(orders_by_status.values())
    
    # Attention needed (New, Waiting Info)
    attention_needed_count = orders_by_status.get(OrderStatus.NEW.value, 0) + \
                             orders_by_status.get(OrderStatus.WAITING_INFO.value, 0)
    
    stats = DashboardStats(
        orders_by_status=orders_by_status,
        total_orders=total_orders,
        attention_needed_count=attention_needed_count
    )
    
    # 2. Revenue calculation (only for Owner)
    revenue_data = []
    if current_user.role == UserRole.OWNER:
        # Sum financials grouped by currency for completed orders
        rev_query = (
            select(
                Order.currency,
                func.sum(Order.total_price).label("tot_rev"),
                func.sum(Order.production_cost).label("tot_prod"),
                func.sum(Order.platform_fee).label("tot_fee"),
                func.sum(Order.shipping_np_cost).label("tot_ship"),
            )
            .where(Order.status == OrderStatus.COMPLETED)
            .group_by(Order.currency)
        )
        rev_result = await db.execute(rev_query)
        
        for curr, rev, prod, fee, ship in rev_result.all():
            rev = float(rev or 0)
            prod = float(prod or 0)
            fee = float(fee or 0)
            ship = float(ship or 0)
            net = rev - prod - fee - ship
            
            revenue_data.append(RevenueByCurrency(
                currency=curr,
                total_revenue=rev,
                total_production_cost=prod,
                total_fees=fee + ship,
                net_profit=net
            ))
            
    return DashboardResponse(
        stats=stats,
        revenue_by_currency=revenue_data
    )
