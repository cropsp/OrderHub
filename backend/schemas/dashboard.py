from datetime import datetime
from pydantic import BaseModel

from schemas.finance import CurrencyAmount


class DashboardStats(BaseModel):
    orders_by_status: dict[str, int]
    total_orders: int
    attention_needed_count: int


class RevenueByCurrency(BaseModel):
    currency: str
    total_revenue: float
    total_production_cost: float
    total_fees: float
    net_profit: float


class DailyRevenue(BaseModel):
    date: str
    revenue: float


class ShopOrderCount(BaseModel):
    shop_name: str
    order_count: int


class RecentActivity(BaseModel):
    id: str
    order_title: str
    from_status: str
    to_status: str
    changed_by: str
    timestamp: datetime


class DashboardResponse(BaseModel):
    stats: DashboardStats
    revenue_by_currency: list[RevenueByCurrency]  # Rendered only for owners
    daily_revenue_trend: list[DailyRevenue] = []
    orders_by_shop: list[ShopOrderCount] = []
    low_stock_packaging_count: int = 0
    unallocated_overhead: list[CurrencyAmount] = []
    # recent_activity: list[RecentActivity] = [] # Optional for later S5-5
