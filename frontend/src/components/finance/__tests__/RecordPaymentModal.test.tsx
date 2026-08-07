import React from 'react'
import { render, screen } from '@testing-library/react'

import RecordPaymentModal from '../RecordPaymentModal'
import type { PartnerSettlement } from '@/api/partnerPayouts'

const PARTNER_ID = 'partner-andriy'

const linkedSettlement: PartnerSettlement = {
  id: 'set-usd',
  shop_id: 'shop-1',
  partner_id: PARTNER_ID,
  partner_name: 'Andriy',
  formula_type: 'profit',
  percent: '15',
  period_start: '2026-05-01',
  period_end: '2026-05-31',
  base_amount: '1000.00',
  base_currency: 'USD',
  computed_amount: '150.00',
  fx_rate_used: null,
  paid_amount: '0.00',
  notes: null,
  created_at: '2026-05-31T12:00:00Z',
  created_by_user_id: 'user-1',
}

vi.mock('@/hooks/usePartnerPayouts', () => ({
  useSettlements: () => ({ data: { items: [linkedSettlement] } }),
  useCreatePayment: () => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
  }),
}))

// PARTNER-CONFIG-1: the partner is picked from this shop's configured partners,
// not typed free-hand, so a payment always carries a real partner_id.
vi.mock('@/hooks/usePartners', () => ({
  useShopPartnerConfigs: () => ({
    data: {
      items: [
        {
          id: 'cfg-1',
          shop_id: 'shop-1',
          partner_id: PARTNER_ID,
          partner_name: 'Andriy',
          percent: '15.00',
          basis: 'profit',
          settlement_currency: 'USD',
          is_active: true,
          last_period_end: null,
        },
      ],
    },
    isLoading: false,
  }),
}))

describe('RecordPaymentModal', () => {
  it('pre-fills the partner and currency from prefillSettlement', () => {
    render(
      <RecordPaymentModal
        isOpen={true}
        onClose={() => {}}
        shopId="shop-1"
        prefillSettlement={linkedSettlement}
      />,
    )
    // Partner select resolves to the settlement's partner_id.
    expect((screen.getByLabelText('Partner') as HTMLSelectElement).value).toBe(
      PARTNER_ID,
    )
    // Currency dropdown shows USD (the settlement's base_currency)
    const currencySelect = screen.getAllByRole('combobox')[2] as HTMLSelectElement
    expect(currencySelect.value).toBe('USD')
  })

  it('shows currency-mismatch warning when payment currency differs from linked settlement', () => {
    render(
      <RecordPaymentModal
        isOpen={true}
        onClose={() => {}}
        shopId="shop-1"
        prefillSettlement={linkedSettlement}
      />,
    )
    // Initial pre-fill matches → no warning yet
    expect(
      screen.queryByText(/Currency differs from linked settlement/i),
    ).not.toBeInTheDocument()
    // Flip currency to UAH while linked settlement is USD → warning shows
    const currencySelect = screen.getAllByRole('combobox')[2] as HTMLSelectElement
    currencySelect.value = 'UAH'
    currencySelect.dispatchEvent(new Event('change', { bubbles: true }))
    // Re-query
    expect(
      screen.getByText(/Currency differs from linked settlement/i),
    ).toBeInTheDocument()
  })
})
