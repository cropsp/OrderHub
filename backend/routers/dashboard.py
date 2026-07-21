import uuid
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy import select, func, cast, Date, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import Capability, User, UserRole
from models.order import Order, OrderStatus
from models.shop import Shop
from models.material import OverheadMaterialReceipt
from models.packaging import PackagingBox
from schemas.dashboard import DashboardResponse, DashboardStats, RevenueByCurrency, DailyRevenue, ShopOrderCount
from schemas.finance import CurrencyAmount
from routers.dependencies import get_current_user, require_role

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard_stats(
    shop_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard statistics and revenue (revenue only shown to owners).

    DASH-PERIOD: when both start_date and end_date are supplied, the financial
    widgets (revenue summary, trend, shop distribution, unallocated overhead)
    are scoped to that inclusive window. The operational widgets — orders by
    status, total_orders, attention_needed_count, low-stock packaging — stay
    live (all-time) regardless: they answer "what needs action now".
    Both dates absent → the previous all-time behaviour, unchanged.
    """
    import logging
    logger = logging.getLogger("dashboard")
    logger.info(f"Fetching dashboard stats for shop_id: {shop_id}, user: {current_user.email}")

    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must be on or before end_date",
        )
    has_period = bool(start_date and end_date)

    # Revenue is realised on fulfillment (shipment), not on order creation.
    # COALESCE protects legacy/imported rows where shipped_at is NULL. Mirrors
    # finance_service._run_kpi_aggregate so the two pages reconcile for the
    # same (shop, period).
    day_col = cast(func.coalesce(Order.shipped_at, Order.ordered_at), Date)

    # Accrual-date window for revenue figures.
    period_filter = []
    # Placement-date window for the shop distribution (an order count, not revenue).
    placed_filter = []
    if has_period:
        period_filter = [day_col >= start_date, day_col <= end_date]
        placed_filter = [
            cast(Order.ordered_at, Date) >= start_date,
            cast(Order.ordered_at, Date) <= end_date,
        ]

    # Base filter
    base_filter = []
    if shop_id and shop_id != "all" and shop_id != "undefined":
        try:
            shop_uuid = uuid.UUID(shop_id)
            base_filter.append(Order.shop_id == shop_uuid)
            logger.info(f"Adding shop filter: {shop_uuid}")
        except ValueError:
            logger.error(f"Invalid shop_id format: {shop_id}")

    if current_user.role == UserRole.DESIGNER:
        base_filter.append(Order.assigned_designer_id == current_user.id)
        logger.info(f"Adding designer filter: {current_user.id}")
    elif current_user.role != UserRole.OWNER:
        # USER-ACCESS-1: manager aggregates sum only over accessible shops.
        from services.access_service import get_shop_scope
        scope = await get_shop_scope(db, current_user)
        if shop_id and shop_id not in ("all", "undefined"):
            try:
                requested = uuid.UUID(shop_id)
            except ValueError:
                requested = None
            if requested is not None and not scope.can_access(requested):
                raise HTTPException(
                    status_code=http_status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this shop",
                )
        if not scope.is_unrestricted:
            base_filter.append(Order.shop_id.in_(scope.shop_ids))

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
    
    # 2. Revenue calculation (money widgets — USER-ACCESS-2 view_finance)
    # Replaces the old owner-only gate: any user with view_finance sees revenue,
    # net profit, the daily trend and unallocated overhead — scoped, for a
    # designer, to their own assigned orders via base_filter. OWNER short-circuits
    # to true inside get_capabilities.
    from services.access_service import get_capabilities
    caps = await get_capabilities(db, current_user)
    can_view_finance = caps.has(Capability.VIEW_FINANCE)
    # view_costs gates itemised costs the same way the finance page does (OQ-3a):
    # revenue + net_profit stay under view_finance; COGS + fees are stripped.
    can_view_costs = caps.has(Capability.VIEW_COSTS)

    revenue_data = []
    daily_trend = []
    if can_view_finance:
        # Summary Revenue (Shipped + Completed)
        rev_query = (
            select(
                Order.currency,
                func.sum(Order.total_price).label("tot_rev"),
                # MAT-5: COGS must match the finance KPI aggregate (computed-first, then manual).
                func.sum(
                    func.coalesce(Order.computed_production_cost, Order.production_cost, 0)
                ).label("tot_prod"),
                func.sum(Order.platform_fee).label("tot_fee"),
                func.sum(Order.shipping_np_cost).label("tot_ship"),
            )
            .where(Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SHIPPED]))
            .where(*base_filter)
            .where(*period_filter)
            .group_by(Order.currency)
        )
        rev_result = await db.execute(rev_query)
        
        for curr, rev, prod, fee, ship in rev_result.all():
            # net_profit is computed from the true figures regardless; the
            # itemised COGS/fees are zeroed on the wire when view_costs is absent
            # (kept consistent with the finance page).
            revenue_data.append(RevenueByCurrency(
                currency=curr,
                total_revenue=float(rev or 0),
                total_production_cost=(
                    float(prod or 0) if can_view_costs else 0.0
                ),
                total_fees=(
                    float(fee or 0) + float(ship or 0) if can_view_costs else 0.0
                ),
                net_profit=float(rev or 0) - float(prod or 0) - float(fee or 0) - float(ship or 0)
            ))

        # Daily Trend — the selected period, or the last 30 days when unscoped.
        # The fallback window is measured on day_col too, so the filter and the
        # GROUP BY agree (pre-DASH-PERIOD it filtered ordered_at while grouping
        # by the COALESCE column).
        if has_period:
            trend_filter = period_filter
        else:
            thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).date()
            trend_filter = [day_col >= thirty_days_ago]
        trend_query = (
            select(
                day_col.label("day"),
                func.sum(Order.total_price).label("daily_rev")
            )
            .where(Order.status.in_([OrderStatus.COMPLETED, OrderStatus.SHIPPED]))
            .where(*trend_filter)
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
        .where(*placed_filter)
        .group_by(Shop.name)
    )
    if current_user.role == UserRole.DESIGNER:
        shop_query = shop_query.where(Order.assigned_designer_id == current_user.id)
        
    shop_result = await db.execute(shop_query)
    orders_by_shop = [ShopOrderCount(shop_name=name, order_count=count) for name, count in shop_result.all()]

    # PKG-2: count of packaging boxes at or below their low-stock threshold.
    low_stock_count = await db.scalar(
        select(func.count(PackagingBox.id)).where(
            PackagingBox.stock_quantity <= PackagingBox.low_stock_threshold
        )
    )

    # MAT-5: per-currency SUM of overhead receipts not tied to any shop.
    # Same audience as the revenue figures (USER-ACCESS-2 view_finance).
    unallocated_overhead: list[CurrencyAmount] = []
    if can_view_finance:
        # DASH-PERIOD: scoped by received_at — the same column
        # finance_service._run_overhead_aggregate filters on.
        overhead_filter = []
        if has_period:
            received_col = cast(OverheadMaterialReceipt.received_at, Date)
            overhead_filter = [received_col >= start_date, received_col <= end_date]
        overhead_query = (
            select(
                OverheadMaterialReceipt.currency,
                func.coalesce(
                    func.sum(OverheadMaterialReceipt.total_cost), 0
                ).label("amount"),
            )
            .where(OverheadMaterialReceipt.shop_id.is_(None))
            .where(*overhead_filter)
            .group_by(OverheadMaterialReceipt.currency)
        )
        overhead_result = await db.execute(overhead_query)
        for currency, amount in overhead_result.all():
            amount_f = float(amount or 0)
            if amount_f != 0:
                unallocated_overhead.append(
                    CurrencyAmount(currency=currency, amount=amount_f)
                )

    return DashboardResponse(
        stats=stats,
        revenue_by_currency=revenue_data,
        daily_revenue_trend=daily_trend,
        orders_by_shop=orders_by_shop,
        low_stock_packaging_count=int(low_stock_count or 0),
        unallocated_overhead=unallocated_overhead,
    )
