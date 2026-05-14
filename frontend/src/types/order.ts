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
  // MAT-4: warnings produced by the SHIPPED-transition mutation response
  // (currency mismatch, partial BOM coverage, negative stock). Empty/absent
  // on plain GETs.
  warnings?: string[];
}

export type OrderListResponse = PaginatedResponse<OrderListItem>

export interface OrderListFilters {
  page?: number
  limit?: number
  status?: OrderStatus
  shop_id?: string
  search?: string
}
