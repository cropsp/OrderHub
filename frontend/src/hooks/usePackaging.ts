import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { packagingApi } from '@/api/packaging'
import { useToastStore } from '@/components/ui/Toast'
import type { PackagingBoxCreate, PackagingBoxUpdate } from '@/types/inventory'
import { getApiErrorMessage } from '@/types/api'

export function usePackaging(includeArchived = false) {
  return useQuery({
    queryKey: ['packaging', { includeArchived }],
    queryFn: () => packagingApi.listPackaging(includeArchived),
  })
}

export function useCreatePackaging() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: ({ data }: { data: PackagingBoxCreate }) =>
      packagingApi.createPackaging(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packaging'] })
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
    mutationFn: ({ id, data }: { id: string; data: PackagingBoxUpdate }) =>
      packagingApi.updatePackaging(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packaging'] })
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
    mutationFn: ({ id }: { id: string }) =>
      packagingApi.deletePackaging(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packaging'] })
      addToast('Packaging archived successfully', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to archive packaging'), 'error')
    }
  })
}

// WH-2: useRestockPackaging is gone with its endpoint. Replenishment goes through
// useCreateMaterialReceipt against box.material_id — see PackagingReceiptModal,
// which re-invalidates ['packaging'] and ['dashboard'] the way this hook did.

export function useBulkImportPackaging() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: ({ importToken }: { importToken: string }) =>
      packagingApi.bulkImportConfirm(importToken),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packaging'] })
      addToast('Import completed successfully', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to complete import'), 'error')
    }
  })
}
