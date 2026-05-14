import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { materialsApi, type MaterialListParams } from '@/api/materials'
import { useToastStore } from '@/components/ui/Toast'
import type { MaterialCreate, MaterialUpdate } from '@/types/inventory'
import { getApiErrorMessage } from '@/types/api'

export function useMaterials(filters: MaterialListParams = {}) {
  return useQuery({
    queryKey: ['materials', filters],
    queryFn: () => materialsApi.list(filters),
  })
}

export function useMaterial(id: string | undefined) {
  return useQuery({
    queryKey: ['materials', id],
    queryFn: () => materialsApi.get(id as string),
    enabled: !!id,
  })
}

export function useCreateMaterial() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: (data: MaterialCreate) => materialsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['materials'] })
      addToast('Material created', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to create material'), 'error')
    },
  })
}

export function useUpdateMaterial() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MaterialUpdate }) =>
      materialsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['materials'] })
      addToast('Material updated', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to update material'), 'error')
    },
  })
}

export function useSoftDeleteMaterial() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: (id: string) => materialsApi.softDelete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['materials'] })
      addToast('Material archived', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to archive material'), 'error')
    },
  })
}
