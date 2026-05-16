export interface CurrencyAmount {
  currency: string;
  amount: number;
}

export interface KpiCard {
  current: CurrencyAmount[];
  previous: CurrencyAmount[];
  change_percent: number | null;
}

export interface OrderCountCard {
  current: number;
  previous: number;
  change_percent: number | null;
}

export interface TimeSeriesPoint {
  date: string;
  currency: string;
  revenue: number;
  net_profit: number;
}

export interface DiagnosticInfo {
  orders_missing_cost: number;
  total_orders_in_period: number;
  orders_with_computed_cost: number;
}

export interface ShopFinanceResponse {
  shop_id: string;
  shop_name: string;
  period_start_iso: string;
  period_end_iso: string;
  granularity: 'day' | 'month';
  revenue: KpiCard;
  cogs: KpiCard;
  fees: KpiCard;
  allocated_overhead_expenses: KpiCard;
  net_profit: KpiCard;
  pipeline_value: KpiCard;
  order_count: OrderCountCard;
  aov: KpiCard;
  time_series: TimeSeriesPoint[];
  diagnostic: DiagnosticInfo;
  // PART-1: informational shipping margin KPI. current=[] when both
  // shipping_revenue and shipping_np_cost are zero — frontend auto-hides.
  shipping_net: KpiCard;
}
