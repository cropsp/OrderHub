import client from './client'

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
}
