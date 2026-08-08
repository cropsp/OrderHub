import client from './client'
import type {
  PackagingBox,
  PackagingBoxCreate,
  PackagingBoxUpdate,
} from '@/types/inventory'

export const packagingApi = {
  listPackaging: async (includeArchived = false) => {
    const response = await client.get<PackagingBox[]>('/packaging-boxes', {
      params: includeArchived ? { include_archived: true } : undefined,
    })
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

  // WH-2: no restockPackaging. Adding units means recording a purchase against
  // the paired material — materialsApi.createReceipt(box.material_id, …) — so
  // packaging replenishment carries a cost by construction.

  // Archives the box (the geometry row and its history survive); kept on DELETE
  // so the call site does not have to move.
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
