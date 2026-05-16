import React from 'react'
import { render, screen } from '@testing-library/react'

import PartnerSettlementsTable from '../PartnerSettlementsTable'
import type { PartnerSettlement } from '@/api/partnerPayouts'

function makeSettlement(
  overrides: Partial<PartnerSettlement> = {},
): PartnerSettlement {
  return {
    id: 'set-1',
    shop_id: 'shop-1',
    partner_name: 'Олег',
    formula_type: 'net_profit_product_only',
    percent: '25',
    period_start: '2026-05-01',
    period_end: '2026-05-31',
    base_amount: '10000.00',
    base_currency: 'UAH',
    computed_amount: '2500.00',
    paid_amount: '0.00',
    notes: null,
    created_at: '2026-05-31T12:00:00Z',
    created_by_user_id: 'user-1',
    ...overrides,
  }
}

describe('PartnerSettlementsTable progress badges', () => {
  it('renders "Unpaid" pill when paid_amount is 0', () => {
    render(
      <PartnerSettlementsTable
        items={[makeSettlement({ paid_amount: '0.00' })]}
        onRecordPayment={() => {}}
        onDelete={() => {}}
      />,
    )
    expect(screen.getByText('Unpaid')).toBeInTheDocument()
  })

  it('renders "Paid in full" pill when paid equals due', () => {
    render(
      <PartnerSettlementsTable
        items={[
          makeSettlement({ computed_amount: '2500.00', paid_amount: '2500.00' }),
        ]}
        onRecordPayment={() => {}}
        onDelete={() => {}}
      />,
    )
    expect(screen.getByText('Paid in full')).toBeInTheDocument()
  })

  it('renders partial-paid pill with X / Y amounts when paid < due', () => {
    render(
      <PartnerSettlementsTable
        items={[
          makeSettlement({ computed_amount: '2500.00', paid_amount: '1000.00' }),
        ]}
        onRecordPayment={() => {}}
        onDelete={() => {}}
      />,
    )
    expect(screen.getByText(/Paid 1,000\.00 UAH \/ 2,500\.00 UAH/)).toBeInTheDocument()
  })

  it('renders "Overpaid by X" pill when paid > due', () => {
    render(
      <PartnerSettlementsTable
        items={[
          makeSettlement({ computed_amount: '2500.00', paid_amount: '3000.00' }),
        ]}
        onRecordPayment={() => {}}
        onDelete={() => {}}
      />,
    )
    expect(screen.getByText(/Overpaid by 500\.00 UAH/)).toBeInTheDocument()
  })
})
