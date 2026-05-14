import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  materialsApi,
  type MaterialListParams,
  type MaterialMovementsParams,
  type MaterialPaginationParams,
} from '@/api/materials'
import { useToastStore } from '@/components/ui/Toast'
import type {
  MaterialCreate,
  MaterialReceiptCreate,
  MaterialStockAdjustment,
  MaterialUpdate,
} from '@/types/inventory'
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

// MAT-2: receipts + ledger + adjustments.

export function useMaterialReceipts(
  id: string | undefined,
  params: MaterialPaginationParams = {},
) {
  return useQuery({
    queryKey: ['material-receipts', id, params],
    queryFn: () => materialsApi.listReceipts(id as string, params),
    enabled: !!id,
  })
}

export function useMaterialMovements(
  id: string | undefined,
  params: MaterialMovementsParams = {},
) {
  return useQuery({
    queryKey: ['material-movements', id, params],
    queryFn: () => materialsApi.listMovements(id as string, params),
    enabled: !!id,
  })
}

export function useCreateMaterialReceipt(id: string | undefined) {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: (data: MaterialReceiptCreate) =>
      materialsApi.createReceipt(id as string, data),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['materials'] })
      queryClient.invalidateQueries({ queryKey: ['materials', id] })
      queryClient.invalidateQueries({ queryKey: ['material-receipts', id] })
      queryClient.invalidateQueries({ queryKey: ['material-movements', id] })

      const { material, receipt } = response
      const unit = material.unit
      const effective = Number(receipt.effective_unit_cost).toFixed(2)
      const newAvg = Number(material.current_unit_cost).toFixed(2)
      const qty = Number(receipt.qty).toFixed(2).replace(/\.?0+$/, '')
      addToast(
        `Прийнято ${qty} ${unit} «${material.name}» за ${effective} ${material.currency}/${unit}. ` +
          `Поточний середній: ${newAvg} ${material.currency}/${unit}.`,
        'success',
      )
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to register receipt'), 'error')
    },
  })
}

export function useAdjustMaterialStock(id: string | undefined) {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: (data: MaterialStockAdjustment) =>
      materialsApi.adjustStock(id as string, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['materials'] })
      queryClient.invalidateQueries({ queryKey: ['materials', id] })
      queryClient.invalidateQueries({ queryKey: ['material-movements', id] })
      addToast('Stock adjusted', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to adjust stock'), 'error')
    },
  })
}
