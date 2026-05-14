import client from './client'
import type {
  OverheadMaterial,
  OverheadMaterialCreate,
  OverheadMaterialReceipt,
  OverheadMaterialReceiptCreate,
  OverheadMaterialUpdate,
} from '@/types/inventory'

export interface OverheadMaterialListParams {
  search?: string
  includeInactive?: boolean
}

export interface OverheadReceiptPaginationParams {
  page?: number
  limit?: number
}

export const overheadMaterialsApi = {
  list: async (params: OverheadMaterialListParams = {}) => {
    const response = await client.get<OverheadMaterial[]>('/overhead-materials', {
      params: {
        search: params.search || undefined,
        include_inactive: params.includeInactive || undefined,
      },
    })
    return response.data
  },

  get: async (id: string) => {
    const response = await client.get<OverheadMaterial>(`/overhead-materials/${id}`)
    return response.data
  },

  create: async (data: OverheadMaterialCreate) => {
    const response = await client.post<OverheadMaterial>('/overhead-materials', data)
    return response.data
  },

  update: async (id: string, data: OverheadMaterialUpdate) => {
    const response = await client.patch<OverheadMaterial>(`/overhead-materials/${id}`, data)
    return response.data
  },

  softDelete: async (id: string) => {
    await client.delete(`/overhead-materials/${id}`)
  },

  createReceipt: async (id: string, data: OverheadMaterialReceiptCreate) => {
    const response = await client.post<OverheadMaterialReceipt>(
      `/overhead-materials/${id}/receipts`,
      data,
    )
    return response.data
  },

  listReceipts: async (
    id: string,
    params: OverheadReceiptPaginationParams = {},
  ) => {
    const response = await client.get<OverheadMaterialReceipt[]>(
      `/overhead-materials/${id}/receipts`,
      {
        params: {
          page: params.page,
          limit: params.limit,
        },
      },
    )
    return response.data
  },
}
