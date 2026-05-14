import client from './client'
import type {
  Material,
  MaterialCreate,
  MaterialMovement,
  MaterialMovementReason,
  MaterialReceipt,
  MaterialReceiptCreate,
  MaterialReceiptResponse,
  MaterialStockAdjustment,
  MaterialUpdate,
} from '@/types/inventory'

export interface MaterialListParams {
  search?: string
  includeInactive?: boolean
}

export interface MaterialPaginationParams {
  page?: number
  limit?: number
}

export interface MaterialMovementsParams extends MaterialPaginationParams {
  reason?: MaterialMovementReason
}

export const materialsApi = {
  list: async (params: MaterialListParams = {}) => {
    const response = await client.get<Material[]>('/materials', {
      params: {
        search: params.search || undefined,
        include_inactive: params.includeInactive || undefined,
      },
    })
    return response.data
  },

  get: async (id: string) => {
    const response = await client.get<Material>(`/materials/${id}`)
    return response.data
  },

  create: async (data: MaterialCreate) => {
    const response = await client.post<Material>('/materials', data)
    return response.data
  },

  update: async (id: string, data: MaterialUpdate) => {
    const response = await client.patch<Material>(`/materials/${id}`, data)
    return response.data
  },

  softDelete: async (id: string) => {
    await client.delete(`/materials/${id}`)
  },

  createReceipt: async (id: string, data: MaterialReceiptCreate) => {
    const response = await client.post<MaterialReceiptResponse>(
      `/materials/${id}/receipts`,
      data,
    )
    return response.data
  },

  listReceipts: async (id: string, params: MaterialPaginationParams = {}) => {
    const response = await client.get<MaterialReceipt[]>(
      `/materials/${id}/receipts`,
      {
        params: {
          page: params.page,
          limit: params.limit,
        },
      },
    )
    return response.data
  },

  listMovements: async (id: string, params: MaterialMovementsParams = {}) => {
    const response = await client.get<MaterialMovement[]>(
      `/materials/${id}/movements`,
      {
        params: {
          page: params.page,
          limit: params.limit,
          reason: params.reason,
        },
      },
    )
    return response.data
  },

  adjustStock: async (id: string, data: MaterialStockAdjustment) => {
    const response = await client.post<Material>(`/materials/${id}/adjust`, data)
    return response.data
  },
}
