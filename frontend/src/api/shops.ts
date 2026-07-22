import client from './client'

import type { ShopListItem } from '@/types/shop'
import type { ShopFinanceResponse } from '@/types/finance'

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

  // ORDER-CARD-1 Part 2: pull Shopify featured images for products missing one.
  backfillProductImages: async (
    id: string,
  ): Promise<{ status: string; eligible: number; updated: number; no_image: number; errors: unknown[] }> => {
    const { data } = await client.post(`/shops/${id}/backfill-product-images`)
    return data
  },

  getShopFinance: async (
    shopId: string,
    startDate: string,
    endDate: string,
  ): Promise<ShopFinanceResponse> => {
    const { data } = await client.get<ShopFinanceResponse>(
      `/shops/${shopId}/finance`,
      { params: { start_date: startDate, end_date: endDate } },
    )
    return data
  },
}
