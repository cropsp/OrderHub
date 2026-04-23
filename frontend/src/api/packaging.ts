import client from './client'
import type { PackagingBox, PackagingBoxCreate, PackagingBoxUpdate } from '@/types/inventory'

export const packagingApi = {
  listPackaging: async (shopId: string) => {
    const response = await client.get<PackagingBox[]>(`/shops/${shopId}/packaging-boxes`)
    return response.data
  },

  createPackaging: async (shopId: string, data: PackagingBoxCreate) => {
    const response = await client.post<PackagingBox>(`/shops/${shopId}/packaging-boxes`, data)
    return response.data
  },

  updatePackaging: async (id: string, data: PackagingBoxUpdate) => {
    const response = await client.patch<PackagingBox>(`/packaging-boxes/${id}`, data)
    return response.data
  },

  deletePackaging: async (id: string) => {
    await client.delete(`/packaging-boxes/${id}`)
  },

  bulkImportPreview: async (shopId: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await client.post(`/shops/${shopId}/packaging-boxes/bulk-csv/preview`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    return response.data
  },

  bulkImportConfirm: async (shopId: string, importToken: string) => {
    const response = await client.post(`/shops/${shopId}/packaging-boxes/bulk-csv/confirm`, {
      import_token: importToken
    })
    return response.data
  }
}
