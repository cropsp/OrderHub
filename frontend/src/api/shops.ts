import client from './client'

import type { ShopListItem } from '@/types/shop'
import type { ShopFinanceResponse } from '@/types/finance'

export interface PlatformFeeBackfillResult {
  status: string
  /** Orders matching the eligibility predicate (NULL fee, not cancelled). */
  matched: number
  /** Of those, the ones already in REVENUE_STATUSES — these move the P&L now. */
  affects_pnl_now: number
  /** The rest: they will count once they ship. */
  pending: number
  fee_total_by_currency: Record<string, number>
  fee_total_pnl_now_by_currency: Record<string, number>
  updated: number
  dry_run: boolean
  fee_percent: number
  /** Immutable settlements overlapping the window — re-pricing under one leaves
   *  that period retroactively over-settled. */
  overlapping_settlements: unknown[]
}

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

  // SHOP-FEE-1: re-price existing orders that never got a platform_fee.
  // dry_run defaults true server-side; pass it explicitly so the caller is
  // always deliberate about which of the two this is.
  backfillPlatformFees: async (
    id: string,
    body: { since?: string | null; until?: string | null; dry_run: boolean },
  ): Promise<PlatformFeeBackfillResult> => {
    const { data } = await client.post<PlatformFeeBackfillResult>(
      `/shops/${id}/backfill-platform-fees`,
      body,
    )
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
