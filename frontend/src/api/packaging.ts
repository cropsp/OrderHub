import client from './client'
import type { PackagingBox, PackagingBoxCreate, PackagingBoxUpdate } from '@/types/inventory'

export const packagingApi = {
  listPackaging: async () => {
    const response = await client.get<PackagingBox[]>('/packaging-boxes')
    return response.data
  },

  createPackaging: async (data: PackagingBoxCreate) => {
    const response = await client.post<PackagingBox>('/packaging-boxes', data)
    return response.data
  },

  updatePackaging: async (id: string, data: PackagingBoxUpdate) => {
    const response = await client.patch<PackagingBox>(`/packaging-boxes/${id}`, data)
    return response.data
  },

  deletePackaging: async (id: string) => {
    await client.delete(`/packaging-boxes/${id}`)
  },

  bulkImportPreview: async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const response = await client.post('/packaging-boxes/bulk-csv/preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    return response.data
  },

  bulkImportConfirm: async (importToken: string) => {
    const response = await client.post('/packaging-boxes/bulk-csv/confirm', {
      import_token: importToken
    })
    return response.data
  }
}
