import React from 'react'
import { render, screen } from '@testing-library/react'

import FinanceKpiCard from '../FinanceKpiCard'
import type { KpiCard, CurrencyAmount } from '@/types/finance'

function fmt(value: number | CurrencyAmount[]): string {
  if (Array.isArray(value)) {
    return value.map((a) => `${a.amount.toFixed(2)} ${a.currency}`).join('\n')
  }
  return value.toLocaleString('en-US')
}

function emptyKpi(): KpiCard {
  return { current: [], previous: [], change_percent: null }
}

describe('Shipping Net KPI conditional rendering', () => {
  it('renders FinanceKpiCard when shipping_net has rows', () => {
    const shippingNet: KpiCard = {
      current: [{ currency: 'UAH', amount: 120.0 }],
      previous: [],
      change_percent: null,
    }
    const { container } = render(
      <>
        {shippingNet.current.length > 0 && (
          <FinanceKpiCard title="Shipping Net" value={shippingNet} formatter={fmt} />
        )}
      </>,
    )
    expect(screen.getByText('Shipping Net')).toBeInTheDocument()
    expect(container.textContent).toContain('120.00 UAH')
  })

  it('does NOT render anything when shipping_net is zero/empty (auto-hide)', () => {
    const shippingNet = emptyKpi()
    const { container } = render(
      <>
        {shippingNet.current.length > 0 && (
          <FinanceKpiCard title="Shipping Net" value={shippingNet} formatter={fmt} />
        )}
      </>,
    )
    expect(screen.queryByText('Shipping Net')).not.toBeInTheDocument()
    expect(container.textContent).toBe('')
  })
})
