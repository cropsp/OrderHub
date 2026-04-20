import { useQuery } from '@tanstack/react-query'

import { ordersApi } from '@/api/orders'
import type { OrderListFilters } from '@/types/order'

type UseOrdersOptions = {
  enabled?: boolean
}

export function useOrders(filters: OrderListFilters = {}, options: UseOrdersOptions = {}) {
  const { enabled = true } = options

  return useQuery({
    queryKey: ['orders', filters],
    queryFn: () => ordersApi.list(filters),
    enabled,
  })
}

export function useOrder(orderId: string | null, options: UseOrdersOptions = {}) {
  const { enabled = true } = options

  return useQuery({
    queryKey: ['orders', orderId],
    queryFn: () => ordersApi.getById(orderId as string),
    enabled: enabled && Boolean(orderId),
  })
}
