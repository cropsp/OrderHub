import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { packagingApi } from '@/api/packaging'
import { useToastStore } from '@/components/ui/Toast'
import type { PackagingBoxCreate, PackagingBoxUpdate } from '@/types/inventory'
import { getApiErrorMessage } from '@/types/api'

export function usePackaging(shopId: string) {
  return useQuery({
    queryKey: ['packaging', shopId],
    queryFn: () => packagingApi.listPackaging(shopId),
    enabled: !!shopId,
  })
}

export function useCreatePackaging() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: ({ shopId, data }: { shopId: string; data: PackagingBoxCreate }) =>
      packagingApi.createPackaging(shopId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['packaging', variables.shopId] })
      addToast('Packaging created successfully', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to create packaging'), 'error')
    }
  })
}

export function useUpdatePackaging() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: ({ id, shopId, data }: { id: string; shopId: string; data: PackagingBoxUpdate }) =>
      packagingApi.updatePackaging(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['packaging', variables.shopId] })
      addToast('Packaging updated successfully', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to update packaging'), 'error')
    }
  })
}

export function useDeletePackaging() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: ({ id, shopId }: { id: string; shopId: string }) =>
      packagingApi.deletePackaging(id),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['packaging', variables.shopId] })
      addToast('Packaging deleted successfully', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to delete packaging'), 'error')
    }
  })
}

export function useBulkImportPackaging() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: ({ shopId, importToken }: { shopId: string; importToken: string }) =>
      packagingApi.bulkImportConfirm(shopId, importToken),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['packaging', variables.shopId] })
      addToast('Import completed successfully', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to complete import'), 'error')
    }
  })
}
