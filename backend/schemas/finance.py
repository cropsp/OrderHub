"""
OrderHub CRM — Finance Schemas (FIN-1)

Pydantic models for the per-shop financial overview endpoint at
/api/shops/{shop_id}/finance. All money values are per-currency lists;
no FX conversion is performed.
"""

from typing import Literal

from pydantic import BaseModel


class CurrencyAmount(BaseModel):
    currency: str
    amount: float


class KpiCard(BaseModel):
    current: list[CurrencyAmount]
    previous: list[CurrencyAmount]
    # change_percent is computed over the primary currency (the one with
    # the largest current.amount). None when previous is zero or no data.
    change_percent: float | None


class OrderCountCard(BaseModel):
    current: int
    previous: int
    change_percent: float | None


class TimeSeriesPoint(BaseModel):
    date: str
    currency: str
    revenue: float
    net_profit: float


class DiagnosticInfo(BaseModel):
    orders_missing_cost: int
    total_orders_in_period: int


class ShopFinanceResponse(BaseModel):
    shop_id: str
    shop_name: str
    period_start_iso: str
    period_end_iso: str
    granularity: Literal["day", "month"]
    revenue: KpiCard
    cogs: KpiCard
    fees: KpiCard
    net_profit: KpiCard
    pipeline_value: KpiCard
    order_count: OrderCountCard
    aov: KpiCard
    time_series: list[TimeSeriesPoint]
    diagnostic: DiagnosticInfo
