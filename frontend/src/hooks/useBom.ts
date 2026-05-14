import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { bomApi } from '@/api/bom'
import { useToastStore } from '@/components/ui/Toast'
import type { BomItemCreate } from '@/types/inventory'
import { getApiErrorMessage } from '@/types/api'

export function useBom(productId: string | undefined) {
  return useQuery({
    queryKey: ['bom', productId],
    queryFn: () => bomApi.get(productId as string),
    enabled: !!productId,
  })
}

export function useBomCost(productId: string | undefined) {
  return useQuery({
    queryKey: ['bom-cost', productId],
    queryFn: () => bomApi.cost(productId as string),
    enabled: !!productId,
  })
}

export function useReplaceBom(productId: string | undefined) {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: (items: BomItemCreate[]) =>
      bomApi.replace(productId as string, items),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bom', productId] })
      queryClient.invalidateQueries({ queryKey: ['bom-cost', productId] })
      queryClient.invalidateQueries({ queryKey: ['products'] })
      addToast('Recipe saved', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to save recipe'), 'error')
    },
  })
}
