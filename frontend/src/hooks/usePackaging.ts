import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { packagingApi } from '@/api/packaging'
import { useToastStore } from '@/components/ui/Toast'
import type { PackagingBoxCreate, PackagingBoxUpdate } from '@/types/inventory'
import { getApiErrorMessage } from '@/types/api'

export function usePackaging() {
  return useQuery({
    queryKey: ['packaging'],
    queryFn: () => packagingApi.listPackaging(),
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
