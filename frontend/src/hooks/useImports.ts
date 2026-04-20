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
