import client from './client'

import type { ShopListItem } from '@/types/shop'

export const shopsApi = {
  list: async (): Promise<ShopListItem[]> => {
    const { data } = await client.get<ShopListItem[]>('/shops')
    return data
  },
  
  create: async (payload: any): Promise<ShopListItem> => {
    const { data } = await client.post<ShopListItem>('/shops', payload)
    return data
  },
  
  update: async (id: string, payload: any): Promise<ShopListItem> => {
    const { data } = await client.patch<ShopListItem>(`/shops/${id}`, payload)
    return data
  },
  
  delete: async (id: string): Promise<void> => {
    await client.delete(`/shops/${id}`)
  },

  sync: async (id: string): Promise<{ status: string; synced_count: number }> => {
    const { data } = await client.post(`/shops/${id}/sync`)
    return data
  },
}
