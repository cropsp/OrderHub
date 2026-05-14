import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  overheadMaterialsApi,
  type OverheadMaterialListParams,
} from '@/api/overheadMaterials'
import { useToastStore } from '@/components/ui/Toast'
import type {
  OverheadMaterialCreate,
  OverheadMaterialUpdate,
} from '@/types/inventory'
import { getApiErrorMessage } from '@/types/api'

export function useOverheadMaterials(filters: OverheadMaterialListParams = {}) {
  return useQuery({
    queryKey: ['overhead-materials', filters],
    queryFn: () => overheadMaterialsApi.list(filters),
  })
}

export function useOverheadMaterial(id: string | undefined) {
  return useQuery({
    queryKey: ['overhead-materials', id],
    queryFn: () => overheadMaterialsApi.get(id as string),
    enabled: !!id,
  })
}

export function useCreateOverheadMaterial() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: (data: OverheadMaterialCreate) => overheadMaterialsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['overhead-materials'] })
      addToast('Overhead material created', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to create overhead material'), 'error')
    },
  })
}

export function useUpdateOverheadMaterial() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: OverheadMaterialUpdate }) =>
      overheadMaterialsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['overhead-materials'] })
      addToast('Overhead material updated', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to update overhead material'), 'error')
    },
  })
}

export function useSoftDeleteOverheadMaterial() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: (id: string) => overheadMaterialsApi.softDelete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['overhead-materials'] })
      addToast('Overhead material archived', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to archive overhead material'), 'error')
    },
  })
}
