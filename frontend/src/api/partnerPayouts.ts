import client from './client'

import type { CurrencyAmount } from '@/types/finance'

export type FormulaType = 'revenue_items_minus_fees' | 'net_profit_product_only'

export interface PartnerSettlement {
  id: string
  shop_id: string
  partner_name: string
  formula_type: FormulaType
  percent: string
  period_start: string
  period_end: string
  base_amount: string
  base_currency: string
  computed_amount: string
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
  formula_type: FormulaType
  percent: string
  period_start: string
  period_end: string
  currency?: string
}

export interface PreviewResponse {
  base_amount: string | null
  base_currency: string | null
  computed_amount: string | null
  available_currencies: CurrencyAmount[]
}

export interface SettlementCreateRequest {
  partner_name: string
  formula_type: FormulaType
  percent: string
  period_start: string
  period_end: string
  currency?: string
  notes?: string | null
}

export interface PaymentCreateRequest {
  partner_name: string
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
    params: { partner?: string; limit?: number; offset?: number } = {},
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
      partner?: string
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

  getPartnerNames: async (shopId: string) => {
    const { data } = await client.get<PartnerNamesResponse>(
      `/shops/${shopId}/partner-payouts/partner-names`,
    )
    return data
  },
}
