import React from 'react'
import { render, screen } from '@testing-library/react'

import RecordPaymentModal from '../RecordPaymentModal'
import type { PartnerSettlement } from '@/api/partnerPayouts'

const linkedSettlement: PartnerSettlement = {
  id: 'set-usd',
  shop_id: 'shop-1',
  partner_name: 'Andriy',
  formula_type: 'net_profit_product_only',
  percent: '15',
  period_start: '2026-05-01',
  period_end: '2026-05-31',
  base_amount: '1000.00',
  base_currency: 'USD',
  computed_amount: '150.00',
  paid_amount: '0.00',
  notes: null,
  created_at: '2026-05-31T12:00:00Z',
  created_by_user_id: 'user-1',
}

vi.mock('@/hooks/usePartnerPayouts', () => ({
  usePartnerNames: () => ({ data: { items: ['Andriy', 'Олег'] } }),
  useSettlements: () => ({ data: { items: [linkedSettlement] } }),
  useCreatePayment: () => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
  }),
}))

describe('RecordPaymentModal', () => {
  it('pre-fills partner name and currency from prefillSettlement', () => {
    render(
      <RecordPaymentModal
        isOpen={true}
        onClose={() => {}}
        shopId="shop-1"
        prefillSettlement={linkedSettlement}
      />,
    )
    // Partner name input pre-filled
    expect(screen.getByDisplayValue('Andriy')).toBeInTheDocument()
    // Currency dropdown shows USD (the settlement's base_currency)
    const currencySelect = screen.getAllByRole('combobox')[1] as HTMLSelectElement
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
    const currencySelect = screen.getAllByRole('combobox')[1] as HTMLSelectElement
    currencySelect.value = 'UAH'
    currencySelect.dispatchEvent(new Event('change', { bubbles: true }))
    // Re-query
    expect(
      screen.getByText(/Currency differs from linked settlement/i),
    ).toBeInTheDocument()
  })
})
