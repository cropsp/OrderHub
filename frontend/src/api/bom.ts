import client from './client'
import type {
  BomCostBreakdown,
  BomItemCreate,
  BomReadResponse,
} from '@/types/inventory'

export const bomApi = {
  get: async (productId: string) => {
    const response = await client.get<BomReadResponse>(
      `/products/${productId}/bom`,
    )
    return response.data
  },

  replace: async (productId: string, items: BomItemCreate[]) => {
    const response = await client.put<BomReadResponse>(
      `/products/${productId}/bom`,
      { items },
    )
    return response.data
  },

  cost: async (productId: string) => {
    const response = await client.get<BomCostBreakdown[]>(
      `/products/${productId}/bom/cost`,
    )
    return response.data
  },
}
