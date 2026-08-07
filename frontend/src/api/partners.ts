import client from './client'

import type {
  Partner,
  PartnerListResponse,
  ShopPartnerConfig,
  ShopPartnerConfigListResponse,
  ShopPartnerConfigUpsert,
} from '@/types/partner'
import type { PartnerBalancesResponse } from './partnerPayouts'

/**
 * Two surfaces, both OWNER-only on the backend:
 *  - /partners        — the global partner IDENTITY (one person, one balance)
 *  - /shops/{id}/partner-config — what that person is owed on one shop
 */
export const partnersApi = {
  list: async (includeInactive = false) => {
    const { data } = await client.get<PartnerListResponse>('/partners', {
      params: includeInactive ? { include_inactive: true } : {},
    })
    return data
  },

  create: async (payload: { name: string; notes?: string | null }) => {
    const { data } = await client.post<Partner>('/partners', payload)
    return data
  },

  update: async (
    partnerId: string,
    payload: { name?: string; is_active?: boolean; notes?: string | null },
  ) => {
    const { data } = await client.patch<Partner>(`/partners/${partnerId}`, payload)
    return data
  },

  /** Every partner's balance across ALL shops. OWNER-only. */
  getAggregateBalances: async () => {
    const { data } = await client.get<PartnerBalancesResponse>('/partners/balances')
    return data
  },

  listShopConfigs: async (shopId: string) => {
    const { data } = await client.get<ShopPartnerConfigListResponse>(
      `/shops/${shopId}/partner-config`,
    )
    return data
  },

  upsertShopConfig: async (
    shopId: string,
    partnerId: string,
    payload: ShopPartnerConfigUpsert,
  ) => {
    const { data } = await client.put<ShopPartnerConfig>(
      `/shops/${shopId}/partner-config/${partnerId}`,
      payload,
    )
    return data
  },

  deleteShopConfig: async (shopId: string, partnerId: string) => {
    await client.delete(`/shops/${shopId}/partner-config/${partnerId}`)
  },
}
