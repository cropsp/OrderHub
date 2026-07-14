import client from './client'
import type { ProductRead, ProductCreate, ProductUpdate } from '@/types/inventory'

export const productsApi = {
  listProducts: async (shopId: string, isActive: boolean = true) => {
    const response = await client.get<ProductRead[]>(`/shops/${shopId}/products`, {
      params: { is_active: isActive }
    })
    return response.data
  },

  createProduct: async (shopId: string, data: ProductCreate) => {
    const response = await client.post<ProductRead>(`/shops/${shopId}/products`, data)
    return response.data
  },

  getProduct: async (id: string) => {
    const response = await client.get<ProductRead>(`/products/${id}`)
    return response.data
  },

  updateProduct: async (id: string, data: ProductUpdate) => {
    const response = await client.patch<ProductRead>(`/products/${id}`, data)
    return response.data
  },

  deleteProduct: async (id: string) => {
    await client.delete(`/products/${id}`)
  },

  uploadImage: async (id: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await client.post<ProductRead>(`/products/${id}/image`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    return response.data
  },

  deleteImage: async (id: string) => {
    await client.delete(`/products/${id}/image`)
  },

  // Blob, not a URL: the access token is an in-memory Authorization header, so
  // only a client-issued request carries auth. Mirrors attachmentsApi.download.
  getImage: async (id: string): Promise<Blob> => {
    const { data } = await client.get(`/products/${id}/image`, { responseType: 'blob' })
    return data
  },

  pullImageFromShopify: async (id: string) => {
    const response = await client.post<ProductRead>(`/products/${id}/image/from-shopify`)
    return response.data
  },

  bulkImportPreview: async (shopId: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await client.post(`/shops/${shopId}/products/bulk-csv/preview`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    return response.data
  },

  bulkImportConfirm: async (shopId: string, importToken: string) => {
    const response = await client.post(`/shops/${shopId}/products/bulk-csv/confirm`, {
      import_token: importToken
    })
    return response.data
  }
}
