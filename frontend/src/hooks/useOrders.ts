import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

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

export function useUpdateOrderStatus() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ orderId, status }: { orderId: string; status: string }) => 
      ordersApi.updateStatus(orderId, status),
    onSuccess: () => {
      // Invalidate all orders queries to trigger a refetch
      void queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}
