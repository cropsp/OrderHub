import { useMutation, useQueryClient } from '@tanstack/react-query'

import { shippingApi } from '@/api/shipping'

export function useCreateTTN() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ orderId, data }: { orderId: string; data: { weight?: number; description?: string } }) =>
      shippingApi.createTTN(orderId, data),
    onSuccess: (_, variables) => {
      // Invalidate both the order detail and the list
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['order', variables.orderId] })
    },
  })
}
