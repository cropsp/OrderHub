import client from './client'
import type {
  BomCostEnvelope,
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

  /** Recipe cost. Pass `inCurrency` (e.g. 'USD') to also get the whole recipe
   *  converted at the current UAH/USD rate — materials are priced in UAH, so
   *  that is what a USD shop's order will actually book. */
  cost: async (productId: string, inCurrency?: string) => {
    const response = await client.get<BomCostEnvelope>(
      `/products/${productId}/bom/cost`,
      inCurrency ? { params: { in: inCurrency } } : undefined,
    )
    return response.data
  },
}
