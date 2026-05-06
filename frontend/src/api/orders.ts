import client from './client'

import type { OrderItem } from '@/types/common'
import type { OrderListFilters, OrderListItem, OrderListResponse } from '@/types/order'

export const ordersApi = {
  list: async (filters: OrderListFilters = {}): Promise<OrderListResponse> => {
    const { data } = await client.get<OrderListResponse>('/orders', { params: filters })
    return data
  },

  getById: async (orderId: string): Promise<OrderListItem> => {
    const { data } = await client.get<OrderListItem>(`/orders/${orderId}`)
    return data
  },

  updateStatus: async (orderId: string, status: string): Promise<OrderListItem> => {
    const { data } = await client.post<OrderListItem>(`/orders/${orderId}/status`, { new_status: status })
    return data
  },

  update: async (orderId: string, payload: any): Promise<OrderListItem> => {
    const { data } = await client.patch<OrderListItem>(`/orders/${orderId}`, payload)
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
