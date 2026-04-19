"""
OrderHub CRM — Dashboard Schemas
"""

from pydantic import BaseModel


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


class DashboardResponse(BaseModel):
    stats: DashboardStats
    revenue_by_currency: list[RevenueByCurrency]  # Rendered only for owners
