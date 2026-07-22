import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { shopsApi } from '@/api/shops'
import { useToastStore } from '@/components/ui/Toast'
import { getApiErrorMessage } from '@/types/api'

type UseShopsOptions = {
  enabled?: boolean
}

export function useShops(options: UseShopsOptions = {}) {
  const { enabled = true } = options

  return useQuery({
    queryKey: ['shops'],
    queryFn: shopsApi.list,
    enabled,
  })
}

export function useCreateShop() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: shopsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shops'] })
    },
  })
}

export function useUpdateShop() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: any }) => shopsApi.update(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shops'] })
    },
  })
}

export function useDeleteShop() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: shopsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shops'] })
    },
  })
}

export function useSyncShop() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => shopsApi.sync(id),
    onSuccess: () => {
      // Invalidate both shops and orders because new orders might have been imported
      queryClient.invalidateQueries({ queryKey: ['shops'] })
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}

export function useBackfillProductImages() {
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  return useMutation({
    mutationFn: (id: string) => shopsApi.backfillProductImages(id),
    onSuccess: (result) => {
      // New images change what order cards + inventory render, so refresh both.
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['products'] })
      addToast(
        `Pulled ${result.updated} image(s) · ${result.no_image} without a featured image`,
        'success',
      )
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to pull product images'), 'error')
    },
  })
}
