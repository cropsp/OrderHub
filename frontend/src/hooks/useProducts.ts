import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { productsApi } from '@/api/products'
import { useToastStore } from '@/components/ui/Toast'
import type { ProductCreate, ProductUpdate } from '@/types/inventory'
import { getApiErrorMessage } from '@/types/api'

export function useProducts(shopId: string, isActive: boolean = true) {
  return useQuery({
    queryKey: ['products', shopId, { isActive }],
    queryFn: () => productsApi.listProducts(shopId, isActive),
    enabled: !!shopId,
  })
}

export function useCreateProduct() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: ({ shopId, data }: { shopId: string; data: ProductCreate }) =>
      productsApi.createProduct(shopId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['products', variables.shopId] })
      addToast('Product created successfully', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to create product'), 'error')
    }
  })
}

export function useUpdateProduct() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: ({ id, shopId, data }: { id: string; shopId: string; data: ProductUpdate }) =>
      productsApi.updateProduct(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['products', variables.shopId] })
      addToast('Product updated successfully', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to update product'), 'error')
    }
  })
}

export function useDeleteProduct() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: ({ id, shopId }: { id: string; shopId: string }) =>
      productsApi.deleteProduct(id),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['products', variables.shopId] })
      addToast('Product archived successfully', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to archive product'), 'error')
    }
  })
}

export function useBulkImportProducts() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn: ({ shopId, importToken }: { shopId: string; importToken: string }) =>
      productsApi.bulkImportConfirm(shopId, importToken),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['products', variables.shopId] })
      addToast('Import completed successfully', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to complete import'), 'error')
    }
  })
}
