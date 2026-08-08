import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { shippingApi } from '@/api/shipping'
import { useDebounce } from './useDebounce'
import { useToastStore } from '@/components/ui/Toast'
import { getApiErrorMessage } from '@/types/api'

export function useCreateTTN() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  
  return useMutation({
    mutationFn: ({ orderId, data }: { orderId: string; data: { 
      weight?: number; 
      volume?: number; 
      length?: number;
      width?: number;
      height?: number;
      description?: string;
      cash_on_delivery?: boolean;
      cod_amount?: number;
      parcel_override?: boolean;
    } }) =>
      shippingApi.createTTN(orderId, data),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['order', variables.orderId] })
      // WH-2: the TTN itself no longer moves stock, but creating one flips the
      // order to SHIPPED, and THAT consumes the box and the BOM materials.
      queryClient.invalidateQueries({ queryKey: ['materials'] })
      queryClient.invalidateQueries({ queryKey: ['packaging'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      addToast('TTN created successfully', 'success')
      for (const warning of data?.warnings ?? []) {
        addToast(warning, 'error')
      }
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to create TTN'), 'error')
    }
  })
}

export function useGetParcelEstimate(orderId: string, enabled: boolean = true) {
  return useQuery({
    queryKey: ['order', orderId, 'parcel-estimate'],
    queryFn: () => shippingApi.getParcelEstimate(orderId),
    enabled: !!orderId && enabled,
    staleTime: 1000 * 60 * 5, // 5 mins
  })
}

export function useDeleteTTN() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  
  return useMutation({
    mutationFn: (orderId: string) => shippingApi.deleteTTN(orderId),
    onSuccess: (data, orderId) => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['order', orderId] })
      // Deleting a TTN gives no stock back (WH-2) — these stay only because the
      // order's own figures move with the status revert.
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      // NP-UX-2: backend returns status='soft_success' when NP reported the
      // TTN was already gone (manual cabinet delete). Surface as info, not
      // success, so the operator knows the local-only cleanup path ran.
      if (data?.status === 'soft_success') {
        addToast(
          data.message ?? 'TTN was already deleted on NP side; local reference cleared.',
          'info',
        )
      } else {
        addToast('TTN deleted successfully', 'success')
      }
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to delete TTN'), 'error')
    }
  })
}

export function useSearchCities(query: string, enabled: boolean = true) {
  const debouncedQuery = useDebounce(query, 350)

  return useQuery({
    queryKey: ['shipping', 'cities', debouncedQuery],
    queryFn: () => shippingApi.searchCities(debouncedQuery),
    // Cities/warehouses are OWNER/MANAGER-only on the backend; `enabled` lets callers
    // (e.g. order detail for a designer) skip the request instead of hitting a 403.
    enabled: enabled && debouncedQuery.length >= 2,
    staleTime: 1000 * 60 * 60, // 1 hour
  })
}

export function useGetWarehouses(cityRef: string, query: string = "", enabled: boolean = true) {
  return useQuery({
    queryKey: ['shipping', 'warehouses', cityRef, query],
    queryFn: () => shippingApi.getWarehouses(cityRef, query),
    enabled: enabled && !!cityRef,
    staleTime: 1000 * 60 * 30, // 30 mins
  })
}

// WB-3 — candidate lookup is triggered on demand (a click), so a mutation fits
// better than a query: it returns the ranked candidate list (or a cached hit).
export function useWbLabelCandidates() {
  return useMutation({
    mutationFn: ({ orderId, broaden = false }: { orderId: string; broaden?: boolean }) =>
      shippingApi.wbLabelCandidates(orderId, broaden),
  })
}

// WB-3 — confirm the parcel and fetch/cache the label. Invalidate the order so
// the ttn_printed flag refreshes; the caller handles printing + error toasts.
export function useWbLabelFetch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ orderId, shipmentId }: { orderId: string; shipmentId: string }) =>
      shippingApi.wbLabelFetch(orderId, shipmentId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['order', variables.orderId] })
      queryClient.invalidateQueries({ queryKey: ['attachments', variables.orderId] })
    },
  })
}
