import type { Order, OrderStatus, PaginatedResponse, OrderItem, OrderStatusHistoryEntry } from './common'

export interface OrderListItem extends Order {
  shop_name: string | null
  customer_name: string | null
  platform: string | null
}

export interface StatusHistoryExtended extends OrderStatusHistoryEntry {
  changed_by_name: string | null;
}

export interface OrderDetail extends OrderListItem {
  items: OrderItem[];
  status_history: StatusHistoryExtended[];
}

export type OrderListResponse = PaginatedResponse<OrderListItem>

export interface OrderListFilters {
  page?: number
  limit?: number
  status?: OrderStatus
  shop_id?: string
  search?: string
}
