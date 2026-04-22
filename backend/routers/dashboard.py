from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, cast, Date, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User, UserRole
from models.order import Order, OrderStatus
from models.shop import Shop
from schemas.dashboard import DashboardResponse, DashboardStats, RevenueByCurrency, DailyRevenue, ShopOrderCount
from routers.dependencies import get_current_user, require_role

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard_stats(
    shop_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard statistics and revenue (revenue only shown to owners)."""
    import logging
    logger = logging.getLogger("dashboard")
    logger.info(f"Fetching dashboard stats for shop_id: {shop_id}, user: {current_user.email}")
    
    # Base filter
    base_filter = []
    if shop_id and shop_id != "all" and shop_id != "undefined":
        try:
            import uuid
            shop_uuid = uuid.UUID(shop_id)
            base_filter.append(Order.shop_id == shop_uuid)
            logger.info(f"Adding shop filter: {shop_uuid}")
        except ValueError:
            logger.error(f"Invalid shop_id format: {shop_id}")

    if current_user.role == UserRole.DESIGNER:
        base_filter.append(Order.assigned_designer_id == current_user.id)
        logger.info(f"Adding designer filter: {current_user.id}")

    # 1. Orders by Status
    status_query = select(Order.status, func.count()).where(*base_filter).group_by(Order.status)
        
    status_result = await db.execute(status_query)
    orders_by_status = {status.value: count for status, count in status_result.all()}
    
    total_orders = sum(orders_by_status.values())
    attention_needed_count = orders_by_status.get(OrderStatus.NEW.value, 0) + \
                             orders_by_status.get(OrderStatus.WAITING_INFO.value, 0) + \
                             orders_by_status.get(OrderStatus.INFO_RECEIVED.value, 0)
    
    stats = DashboardStats(
        orders_by_status=orders_by_status,
        total_orders=total_orders,
        attention_needed_count=attention_needed_count
    )
    
    # 2. Revenue calculation (only for Owner)
    revenue_data = []
    daily_trend = []
    if current_user.role == UserRole.OWNER:
        # Summary Revenue (Shipped + Completed)
        rev_query = (
            select(
                Order.currency,
                func.sum(Order.total_price).label("tot_rev"),
                func.sum(Order.production_cost).label("tot_prod"),
                func.sum(Order.platform_fee).label("tot_fee"),
                func.sum(Order.shipping_np_cost).label("tot_ship"),
            )
            .where(Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SHIPPED]))
            .where(*base_filter)
            .group_by(Order.currency)
        )
        rev_result = await db.execute(rev_query)
        
        for curr, rev, prod, fee, ship in rev_result.all():
            revenue_data.append(RevenueByCurrency(
                currency=curr,
                total_revenue=float(rev or 0),
                total_production_cost=float(prod or 0),
                total_fees=float(fee or 0) + float(ship or 0),
                net_profit=float(rev or 0) - float(prod or 0) - float(fee or 0) - float(ship or 0)
            ))

        # Daily Trend (Last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        day_col = cast(Order.ordered_at, Date)
        trend_query = (
            select(
                day_col.label("day"),
                func.sum(Order.total_price).label("daily_rev")
            )
            .where(Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SHIPPED]))
            .where(Order.ordered_at >= thirty_days_ago)
            .where(*base_filter)
            .group_by(day_col)
            .order_by(day_col)
        )
        trend_result = await db.execute(trend_query)
        for day, rev in trend_result.all():
            date_str = day.isoformat() if hasattr(day, "isoformat") else str(day)
            daily_trend.append(DailyRevenue(date=date_str, revenue=float(rev or 0)))

    # 3. Shop Breakdown
    shop_query = (
        select(Shop.name, func.count(Order.id))
        .join(Order, Order.shop_id == Shop.id)
        .where(*base_filter)
        .group_by(Shop.name)
    )
    if current_user.role == UserRole.DESIGNER:
        shop_query = shop_query.where(Order.assigned_designer_id == current_user.id)
        
    shop_result = await db.execute(shop_query)
    orders_by_shop = [ShopOrderCount(shop_name=name, order_count=count) for name, count in shop_result.all()]
            
    return DashboardResponse(
        stats=stats,
        revenue_by_currency=revenue_data,
        daily_revenue_trend=daily_trend,
        orders_by_shop=orders_by_shop
    )
