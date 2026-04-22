import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { shippingApi } from '@/api/shipping'

export function useCreateTTN() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ orderId, data }: { orderId: string; data: { weight?: number; description?: string } }) =>
      shippingApi.createTTN(orderId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['order', variables.orderId] })
    },
  })
}

export function useSearchCities(query: string) {
  return useQuery({
    queryKey: ['shipping', 'cities', query],
    queryFn: () => shippingApi.searchCities(query),
    enabled: query.length >= 2,
    staleTime: 1000 * 60 * 60, // 1 hour
  })
}

export function useGetWarehouses(cityRef: string, query: string = "") {
  return useQuery({
    queryKey: ['shipping', 'warehouses', cityRef, query],
    queryFn: () => shippingApi.getWarehouses(cityRef, query),
    enabled: !!cityRef,
    staleTime: 1000 * 60 * 30, // 30 mins
  })
}
