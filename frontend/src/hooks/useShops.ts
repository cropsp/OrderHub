import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { shopsApi } from '@/api/shops'

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
