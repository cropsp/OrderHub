import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { shippingApi } from '@/api/shipping'
import { useDebounce } from './useDebounce'
import { useToastStore } from '@/components/ui/Toast'

export function useCreateTTN() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  
  return useMutation({
    mutationFn: ({ orderId, data }: { orderId: string; data: { 
      weight?: number; 
      volume?: number; 
      description?: string;
      cash_on_delivery?: boolean;
      cod_amount?: number;
    } }) =>
      shippingApi.createTTN(orderId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['order', variables.orderId] })
      addToast('TTN created successfully', 'success')
    },
    onError: (error: any) => {
      const msg = error.response?.data?.detail || 'Failed to create TTN'
      addToast(msg, 'error')
    }
  })
}

export function useDeleteTTN() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  
  return useMutation({
    mutationFn: (orderId: string) => shippingApi.deleteTTN(orderId),
    onSuccess: (_, orderId) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['order', orderId] })
      addToast('TTN deleted successfully', 'success')
    },
    onError: (error: any) => {
      const msg = error.response?.data?.detail || 'Failed to delete TTN'
      addToast(msg, 'error')
    }
  })
}

export function useSearchCities(query: string) {
  const debouncedQuery = useDebounce(query, 350)
  
  return useQuery({
    queryKey: ['shipping', 'cities', debouncedQuery],
    queryFn: () => shippingApi.searchCities(debouncedQuery),
    enabled: debouncedQuery.length >= 2,
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
