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

export function useProduct(id: string | undefined) {
  return useQuery({
    queryKey: ['product', id],
    queryFn: () => productsApi.getProduct(id as string),
    enabled: !!id,
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
      queryClient.invalidateQueries({ queryKey: ['product', variables.id] })
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

/**
 * Fetches the product image as a Blob. Gated on `hasImage` (from
 * `product.image_url`) so products without one never issue a request.
 */
export function useProductImage(id: string | undefined, hasImage: boolean) {
  return useQuery({
    queryKey: ['product-image', id],
    queryFn: () => productsApi.getImage(id as string),
    enabled: !!id && hasImage,
  })
}

function useProductImageMutation<TVars extends { id: string; shopId: string }>(
  mutationFn: (variables: TVars) => Promise<unknown>,
  successMessage: string,
  errorMessage: string,
) {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  return useMutation({
    mutationFn,
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['products', variables.shopId] })
      queryClient.invalidateQueries({ queryKey: ['product', variables.id] })
      queryClient.invalidateQueries({ queryKey: ['product-image', variables.id] })
      addToast(successMessage, 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, errorMessage), 'error')
    }
  })
}

export function useUploadProductImage() {
  return useProductImageMutation(
    ({ id, file }: { id: string; shopId: string; file: File }) =>
      productsApi.uploadImage(id, file),
    'Image updated successfully',
    'Failed to upload image',
  )
}

export function useDeleteProductImage() {
  return useProductImageMutation(
    ({ id }: { id: string; shopId: string }) => productsApi.deleteImage(id),
    'Image removed successfully',
    'Failed to remove image',
  )
}

export function usePullProductImageFromShopify() {
  return useProductImageMutation(
    ({ id }: { id: string; shopId: string }) => productsApi.pullImageFromShopify(id),
    'Image pulled from Shopify',
    'Failed to pull image from Shopify',
  )
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
