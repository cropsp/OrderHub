import { useMutation, useQueryClient } from '@tanstack/react-query'
import { importsApi } from '@/api/imports'

export function useImportEtsyCsv() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ shopId, file }: { shopId: string; file: File }) =>
      importsApi.importEtsyCsv(shopId, file),
    onSuccess: () => {
      // Refresh orders list since new orders were created
      queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
  })
}

export function useImportEtsyStatement() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ shopId, file }: { shopId: string; file: File }) =>
      importsApi.importEtsyStatement(shopId, file),
    onSuccess: () => {
      // The import rewrites order.platform_fee and books monthly overhead, so
      // every surface that reads either is now stale.
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['finance'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['overhead-materials'] })
    },
  })
}
