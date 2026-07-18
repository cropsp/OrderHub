import client from './client'

import type { OrderItem } from '@/types/common'
import type {
  BulkStatusResult,
  OrderDetail,
  OrderListFilters,
  OrderListItem,
  OrderListResponse,
} from '@/types/order'
import type { AddressVerdict } from '@/types/addressValidation'

export const ordersApi = {
  list: async (filters: OrderListFilters = {}): Promise<OrderListResponse> => {
    const { data } = await client.get<OrderListResponse>('/orders', { params: filters })
    return data
  },

  getById: async (orderId: string): Promise<OrderListItem> => {
    const { data } = await client.get<OrderListItem>(`/orders/${orderId}`)
    return data
  },

  updateStatus: async (orderId: string, status: string): Promise<OrderDetail> => {
    // MAT-4: response carries `warnings: string[]` populated by the SHIPPED
    // consumption hook (currency mismatch, partial BOM, negative stock).
    const { data } = await client.post<OrderDetail>(`/orders/${orderId}/status`, { new_status: status })
    return data
  },

  bulkUpdateStatus: async (
    orderIds: string[],
    status: string,
    comment?: string,
  ): Promise<BulkStatusResult> => {
    // One call for the whole batch; the response classifies each order as
    // updated / unchanged / skipped.
    const { data } = await client.post<BulkStatusResult>('/orders/bulk-status', {
      order_ids: orderIds,
      new_status: status,
      comment,
    })
    return data
  },

  update: async (
    orderId: string,
    payload: Record<string, unknown> & { packaging_id?: string | null },
  ): Promise<OrderListItem> => {
    const { data } = await client.patch<OrderListItem>(`/orders/${orderId}`, payload)
    return data
  },

  // ADDR-VAL-2: advisory address check (ADDR-VAL-1 endpoint). Never mutates the
  // order — Apply goes through `update` above.
  validateAddress: async (orderId: string): Promise<AddressVerdict> => {
    const { data } = await client.post<AddressVerdict>(`/orders/${orderId}/validate-address`)
    return data
  },

  create: async (payload: any): Promise<OrderListItem> => {
    const { data } = await client.post<OrderListItem>('/orders', payload)
    return data
  },

  addItem: async (
    orderId: string,
    payload: {
      title: string
      quantity: number
      unit_price: number
      product_variant_id?: string
      sku?: string
      variations?: string
    },
  ): Promise<OrderItem> => {
    const { data } = await client.post<OrderItem>(`/orders/${orderId}/items`, payload)
    return data
  },

  updateItem: async (
    itemId: string,
    payload: {
      title?: string
      quantity?: number
      unit_price?: number
      product_variant_id?: string
    },
  ): Promise<OrderItem> => {
    const { data } = await client.patch<OrderItem>(`/orders/items/${itemId}`, payload)
    return data
  },

  deleteItem: async (itemId: string): Promise<void> => {
    await client.delete(`/orders/items/${itemId}`)
  },
};
