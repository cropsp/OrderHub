import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'

import PartnerSettlementsTable from '../PartnerSettlementsTable'
import type { PartnerSettlement } from '@/api/partnerPayouts'

function makeSettlement(
  overrides: Partial<PartnerSettlement> = {},
): PartnerSettlement {
  return {
    id: 'set-1',
    shop_id: 'shop-1',
    partner_id: 'partner-1',
    partner_name: 'Олег',
    formula_type: 'profit',
    percent: '25',
    period_start: '2026-05-01',
    period_end: '2026-05-31',
    base_amount: '10000.00',
    base_currency: 'UAH',
    computed_amount: '2500.00',
    fx_rate_used: null,
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


describe('PartnerSettlementsTable staleness (PARTNER-CONFIG-1)', () => {
  it('renders a Stale badge with its reason when the base has moved', () => {
    render(
      <PartnerSettlementsTable
        items={[makeSettlement()]}
        onRecordPayment={() => {}}
        onDelete={() => {}}
        staleness={{
          'set-1': {
            settlement_id: 'set-1',
            stale: true,
            recomputed_base_amount: '9800.00',
            reason: 'Base moved from 10000.00 to 9800.00 UAH',
          },
        }}
      />,
    )
    const badge = screen.getByText('Stale')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveAttribute('title', 'Base moved from 10000.00 to 9800.00 UAH')
  })

  it('renders no badge when the settlement is still current', () => {
    render(
      <PartnerSettlementsTable
        items={[makeSettlement()]}
        onRecordPayment={() => {}}
        onDelete={() => {}}
        staleness={{
          'set-1': {
            settlement_id: 'set-1',
            stale: false,
            recomputed_base_amount: '10000.00',
            reason: null,
          },
        }}
      />,
    )
    expect(screen.queryByText('Stale')).not.toBeInTheDocument()
  })

  it('only offers the check button when a handler is wired', () => {
    const onCheck = vi.fn()
    const { unmount } = render(
      <PartnerSettlementsTable
        items={[makeSettlement()]}
        onRecordPayment={() => {}}
        onDelete={() => {}}
      />,
    )
    expect(
      screen.queryByRole('button', { name: /Check for changes/i }),
    ).not.toBeInTheDocument()
    unmount()

    render(
      <PartnerSettlementsTable
        items={[makeSettlement()]}
        onRecordPayment={() => {}}
        onDelete={() => {}}
        onCheckStaleness={onCheck}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /Check for changes/i }))
    expect(onCheck).toHaveBeenCalledTimes(1)
  })

  it('labels legacy formulas as legacy so old settlements stay readable', () => {
    render(
      <PartnerSettlementsTable
        items={[
          makeSettlement({
            id: 'legacy-1',
            formula_type: 'revenue_items_minus_fees',
          }),
        ]}
        onRecordPayment={() => {}}
        onDelete={() => {}}
      />,
    )
    expect(screen.getByText('Items − Fees (legacy)')).toBeInTheDocument()
  })
})
