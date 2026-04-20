import type { Order, OrderStatus, PaginatedResponse } from './common'

export interface OrderListItem extends Order {
  shop_name: string | null
  customer_name: string | null
  platform: string | null
}

export type OrderListResponse = PaginatedResponse<OrderListItem>

export interface OrderListFilters {
  page?: number
  limit?: number
  status?: OrderStatus
  shop_id?: string
  search?: string
}
