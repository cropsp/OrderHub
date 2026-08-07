import client from './client'

import type { CurrencyAmount } from '@/types/finance'
import type {
  BasisType,
  SelectableBasis,
  SettlementStalenessResponse,
} from '@/types/partner'

/**
 * All four values, because a settlement is an immutable historical fact and a
 * PART-1 row must still deserialise. Only `SelectableBasis` (turnover | profit)
 * may be SENT — see types/partner.ts.
 */
export type FormulaType = BasisType

export interface PartnerSettlement {
  id: string
  shop_id: string
  partner_id: string
  partner_name: string
  formula_type: FormulaType
  percent: string
  period_start: string
  period_end: string
  base_amount: string
  base_currency: string
  computed_amount: string
  /** UAH per 1 USD, frozen at Calculate time. null = no conversion applied. */
  fx_rate_used: string | null
  paid_amount: string
  notes: string | null
  created_at: string
  created_by_user_id: string
}

export interface PartnerSettlementListResponse {
  items: PartnerSettlement[]
  total: number
}

export interface PartnerPayment {
  id: string
  shop_id: string
  partner_id: string
  partner_name: string
  settlement_id: string | null
  amount: string
  currency: string
  paid_at: string
  notes: string | null
  created_at: string
  created_by_user_id: string
}

export interface PartnerPaymentListResponse {
  items: PartnerPayment[]
  total: number
}

export interface PartnerBalance {
  partner_id: string
  partner_name: string
  currency: string
  total_settled: string
  total_paid: string
  balance_owed: string
}

export interface PartnerBalancesResponse {
  items: PartnerBalance[]
}

export interface PartnerNamesResponse {
  items: string[]
}

export interface PreviewRequest {
  partner_id?: string | null
  formula_type: FormulaType
  percent: string
  period_start: string
  period_end: string
  currency?: string
}

/** One component of the base, before and after FX. Cost terms (cogs,
 *  non_shipping_fees, allocated_overhead) are stripped for callers without
 *  view_costs, so never assume a fixed set. */
export interface BaseTermDetail {
  name: string
  currency: string
  amount: string
  converted: string
}

/** Rule 7 warnings. `fx_blocker` is the exception — it is why Create will 422. */
export interface BaseQualityPanel {
  total_orders: number
  orders_missing_cost: number
  orders_missing_platform_fee: number
  etsy_months_without_statement: string[]
  etsy_refunds_unbooked: boolean
  fx_blocker: string | null
}

export interface OverlappingSettlement {
  id: string
  period_start: string
  period_end: string
}

export interface PreviewResponse {
  base_amount: string | null
  base_currency: string | null
  computed_amount: string | null
  available_currencies: CurrencyAmount[]
  fx_rate_used: string | null
  terms: BaseTermDetail[]
  quality: BaseQualityPanel | null
  /** Non-empty means Create will be refused with a 422. */
  overlapping: OverlappingSettlement[]
  last_period_end: string | null
}

export interface SettlementCreateRequest {
  partner_id: string
  formula_type: SelectableBasis
  percent: string
  period_start: string
  period_end: string
  notes?: string | null
}

export interface PaymentCreateRequest {
  partner_id: string
  settlement_id?: string | null
  amount: string
  currency: string
  paid_at: string
  notes?: string | null
}

export const partnerPayoutsApi = {
  preview: async (shopId: string, payload: PreviewRequest) => {
    const { data } = await client.post<PreviewResponse>(
      `/shops/${shopId}/partner-payouts/preview`,
      payload,
    )
    return data
  },

  createSettlement: async (shopId: string, payload: SettlementCreateRequest) => {
    const { data } = await client.post<PartnerSettlement>(
      `/shops/${shopId}/partner-payouts/settlements`,
      payload,
    )
    return data
  },

  listSettlements: async (
    shopId: string,
    params: { partner_id?: string; limit?: number; offset?: number } = {},
  ) => {
    const { data } = await client.get<PartnerSettlementListResponse>(
      `/shops/${shopId}/partner-payouts/settlements`,
      { params },
    )
    return data
  },

  deleteSettlement: async (shopId: string, settlementId: string) => {
    await client.delete(
      `/shops/${shopId}/partner-payouts/settlements/${settlementId}`,
    )
  },

  createPayment: async (shopId: string, payload: PaymentCreateRequest) => {
    const { data } = await client.post<PartnerPayment>(
      `/shops/${shopId}/partner-payouts/payments`,
      payload,
    )
    return data
  },

  listPayments: async (
    shopId: string,
    params: {
      partner_id?: string
      settlement_id?: string
      limit?: number
      offset?: number
    } = {},
  ) => {
    const { data } = await client.get<PartnerPaymentListResponse>(
      `/shops/${shopId}/partner-payouts/payments`,
      { params },
    )
    return data
  },

  deletePayment: async (shopId: string, paymentId: string) => {
    await client.delete(`/shops/${shopId}/partner-payouts/payments/${paymentId}`)
  },

  getBalances: async (shopId: string) => {
    const { data } = await client.get<PartnerBalancesResponse>(
      `/shops/${shopId}/partner-payouts/balances`,
    )
    return data
  },

  checkStaleness: async (shopId: string, limit = 25) => {
    const { data } = await client.get<SettlementStalenessResponse>(
      `/shops/${shopId}/partner-payouts/settlements/staleness`,
      { params: { limit } },
    )
    return data
  },

  getPartnerNames: async (shopId: string) => {
    const { data } = await client.get<PartnerNamesResponse>(
      `/shops/${shopId}/partner-payouts/partner-names`,
    )
    return data
  },
}
