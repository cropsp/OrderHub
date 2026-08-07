/**
 * Hand-written mirror of backend/schemas/partner.py (PARTNER-CONFIG-1).
 * There is no codegen — if you change a Pydantic field name or type, change it
 * here too. Money and percentages arrive as strings (Decimal serialisation),
 * same convention as types/fx.ts.
 */

/** Mirrors models.partner_settlement.PartnerSettlementFormula. */
export type BasisType =
  | 'revenue_items_minus_fees'
  | 'net_profit_product_only'
  | 'turnover'
  | 'profit'

/**
 * The only two selectable for a new config or settlement. The legacy pair stays
 * readable forever — settlements are immutable historical facts — but is not
 * offered anywhere in the UI. Mirrors SelectableBasisLiteral.
 */
export type SelectableBasis = 'turnover' | 'profit'

export const BASIS_LABELS: Record<BasisType, string> = {
  turnover: 'Turnover',
  profit: 'Profit',
  revenue_items_minus_fees: 'Items − fees (legacy)',
  net_profit_product_only: 'Net profit, product only (legacy)',
}

export const BASIS_HELP: Record<SelectableBasis, string> = {
  turnover:
    'Item revenue less the discount you funded, less refunds dated in this period. Before platform fees, before costs, excluding shipping.',
  profit:
    'Turnover less COGS, platform fees and this shop’s allocated overhead. Excludes shipping economics — not the same as the Finance page net profit.',
}

export interface Partner {
  id: string
  name: string
  is_active: boolean
  notes: string | null
  created_at: string
  updated_at: string
}

export interface PartnerListResponse {
  items: Partner[]
}

export interface ShopPartnerConfig {
  id: string
  shop_id: string
  partner_id: string
  partner_name: string
  percent: string
  basis: SelectableBasis
  settlement_currency: string
  is_active: boolean
  /** period_end of this partner's latest settlement on this shop, or null. */
  last_period_end: string | null
}

export interface ShopPartnerConfigListResponse {
  items: ShopPartnerConfig[]
}

export interface ShopPartnerConfigUpsert {
  percent: string
  basis: SelectableBasis
  settlement_currency: string
  is_active: boolean
}

export interface SettlementStaleness {
  settlement_id: string
  stale: boolean
  recomputed_base_amount: string | null
  reason: string | null
}

export interface SettlementStalenessResponse {
  items: SettlementStaleness[]
  checked_count: number
  truncated: boolean
}
