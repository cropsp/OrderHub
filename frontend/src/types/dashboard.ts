export interface DashboardStats {
  orders_by_status: Record<string, number>;
  total_orders: number;
  attention_needed_count: number;
}

export interface RevenueByCurrency {
  currency: string;
  total_revenue: number;
  total_production_cost: number;
  total_fees: number;
  net_profit: number;
}

export interface DailyRevenue {
  date: string;
  revenue: number;
}

export interface ShopOrderCount {
  shop_name: string;
  order_count: number;
}

export interface DashboardResponse {
  stats: DashboardStats;
  revenue_by_currency: RevenueByCurrency[];
  daily_revenue_trend: DailyRevenue[];
  orders_by_shop: ShopOrderCount[];
}
