import type { Order, OrderStatus, PaginatedResponse, OrderItem, OrderStatusHistoryEntry } from './common'
import type { AddressValidationStatus } from './addressValidation'

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
  // ADDR-VAL-2: last-known address-validation outcome, persisted by ADDR-VAL-1,
  // so the order-detail badge renders on load without a fresh Google call.
  address_validation_status?: AddressValidationStatus | null;
  address_validation_at?: string | null;
}

export type OrderListResponse = PaginatedResponse<OrderListItem>

export interface BulkStatusSkippedItem {
  order_id: string
  reason: string
}

/** Per-order outcome summary returned by POST /orders/bulk-status. */
export interface BulkStatusResult {
  updated: number
  unchanged: number
  skipped: BulkStatusSkippedItem[]
  warnings: string[]
}

export interface OrderListFilters {
  page?: number
  limit?: number
  status?: OrderStatus
  shop_id?: string
  search?: string
}
