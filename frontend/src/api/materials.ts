import client from './client'
import type {
  Material,
  MaterialCreate,
  MaterialUpdate,
} from '@/types/inventory'

export interface MaterialListParams {
  search?: string
  includeInactive?: boolean
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
}
