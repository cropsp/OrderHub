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
    mutationFn: ({
      shopId,
      file,
      dryRun,
    }: {
      shopId: string
      file: File
      dryRun: boolean
    }) => importsApi.importEtsyStatement(shopId, file, dryRun),
    onSuccess: (_report, { dryRun }) => {
      // A dry run rolled itself back — nothing on the server moved, so nothing
      // is stale. Only a real import rewrites order.platform_fee and books the
      // monthly overhead rows.
      if (dryRun) return
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      queryClient.invalidateQueries({ queryKey: ['finance'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['overhead-materials'] })
    },
  })
}
