import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ordersApi } from '@/api/orders'
import { useToastStore } from '@/components/ui/Toast'
import type { OrderListFilters, OrderDetail } from '@/types/order'

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
    queryFn: () => ordersApi.getById(orderId as string) as Promise<OrderDetail>,
    enabled: enabled && Boolean(orderId),
  })
}

export function useUpdateOrderStatus() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: ({ orderId, status }: { orderId: string; status: string }) =>
      ordersApi.updateStatus(orderId, status),
    onSuccess: (data, { orderId }) => {
      // Invalidate both the list and the specific order to trigger refetch
      void queryClient.invalidateQueries({ queryKey: ['orders'] })
      void queryClient.invalidateQueries({ queryKey: ['orders', orderId] })
      // MAT-4: surface SHIPPED-transition warnings as toasts.
      // ⚠ prefix → error (amber); ⓘ → info; anything else → info.
      for (const warning of data?.warnings ?? []) {
        addToast(warning, warning.startsWith('⚠') ? 'error' : 'info')
      }
    },
  })
}

export function useUpdateOrder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ orderId, payload }: { orderId: string; payload: any }) => 
      ordersApi.update(orderId, payload),
    onSuccess: (_, { orderId }) => {
      void queryClient.invalidateQueries({ queryKey: ['orders'] })
      void queryClient.invalidateQueries({ queryKey: ['orders', orderId] })
    },
  })
}

export function useCreateOrder() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: any) => ordersApi.create(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}

type AddItemVars = {
  orderId: string
  title: string
  quantity: number
  unit_price: number
  product_variant_id?: string
  sku?: string
  variations?: string
}

export function useAddOrderItem() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ orderId, ...payload }: AddItemVars) => ordersApi.addItem(orderId, payload),
    onSuccess: (_, { orderId }) => {
      void queryClient.invalidateQueries({ queryKey: ['orders'] })
      void queryClient.invalidateQueries({ queryKey: ['orders', orderId] })
    },
  })
}

type UpdateItemVars = {
  orderId: string
  itemId: string
  title?: string
  quantity?: number
  unit_price?: number
  product_variant_id?: string
}

export function useUpdateOrderItem() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (vars: UpdateItemVars) =>
      ordersApi.updateItem(vars.itemId, {
        title: vars.title,
        quantity: vars.quantity,
        unit_price: vars.unit_price,
        product_variant_id: vars.product_variant_id,
      }),
    onSuccess: (_, { orderId }) => {
      void queryClient.invalidateQueries({ queryKey: ['orders'] })
      void queryClient.invalidateQueries({ queryKey: ['orders', orderId] })
    },
  })
}

export function useDeleteOrderItem() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ itemId }: { orderId: string; itemId: string }) => ordersApi.deleteItem(itemId),
    onSuccess: (_, { orderId }) => {
      void queryClient.invalidateQueries({ queryKey: ['orders'] })
      void queryClient.invalidateQueries({ queryKey: ['orders', orderId] })
    },
  })
}
