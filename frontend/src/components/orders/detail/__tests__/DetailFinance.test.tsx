import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { OrderDetail } from '@/types/order'

import { DetailFinance } from '../DetailFinance'

function makeOrder(overrides: Partial<OrderDetail> = {}): OrderDetail {
  return {
    id: 'order-1',
    external_id: 'EXT-1',
    shop_id: 'shop-1',
    customer_id: 'cust-1',
    status: 'shipped' as OrderDetail['status'],
    title: 'Test Order',
    total_price: 1000,
    currency: 'UAH',
    production_cost: null,
    computed_production_cost: null,
    cogs_fx_rate: null,
    cogs_basis_amount: null,
    cogs_basis_currency: null,
    shipping_np_cost: null,
    platform_fee: null,
    shipping_name: null,
    shipping_phone: null,
    shipping_street_1: null,
    shipping_street_2: null,
    shipping_city: null,
    shipping_state: null,
    shipping_zip: null,
    shipping_country: null,
    shipping_city_ref: null,
    shipping_warehouse_ref: null,
    assigned_designer_id: null,
    assigned_at: null,
    ttn_number: null,
    ttn_created_at: null,
    ttn_printed: false,
    customer_note: null,
    custom_info: null,
    internal_note: null,
    ordered_at: '2026-05-14T10:00:00Z',
    shipped_at: null,
    completed_at: null,
    created_at: '2026-05-14T10:00:00Z',
    updated_at: '2026-05-14T10:00:00Z',
    parcel_override: false,
    shop_name: 'KoraKlenu',
    customer_name: 'Test Customer',
    platform: 'manual',
    items: [],
    status_history: [],
    ...overrides,
  }
}

describe('DetailFinance — MAT-4 cost display', () => {
  it('renders manual production cost when only production_cost is set', () => {
    // total_price 1000 − cost 300 = net profit 700, so 300.00 is unambiguous.
    render(
      <DetailFinance
        order={makeOrder({
          production_cost: 300,
          computed_production_cost: null,
        })}
      />,
    )
    expect(screen.getByText('Production cost')).toBeInTheDocument()
    expect(screen.getByText('300.00')).toBeInTheDocument()
    expect(screen.queryByText('Computed cost (from BOM)')).toBeNull()
    expect(screen.queryByTestId('variance-badge')).toBeNull()
  })

  it('renders computed cost row when computed_production_cost is set', () => {
    render(
      <DetailFinance
        order={makeOrder({
          production_cost: null,
          computed_production_cost: 750,
        })}
      />,
    )
    expect(screen.getByText('Computed cost (from BOM)')).toBeInTheDocument()
    expect(screen.getByText('750.00')).toBeInTheDocument()
    // No manual cost row.
    expect(screen.queryByText('Production cost')).toBeNull()
    // No variance badge without both values.
    expect(screen.queryByTestId('variance-badge')).toBeNull()
  })

  it('hides computed row when computed_production_cost is null', () => {
    render(
      <DetailFinance
        order={makeOrder({
          production_cost: 500,
          computed_production_cost: null,
        })}
      />,
    )
    expect(screen.queryByText('Computed cost (from BOM)')).toBeNull()
  })

  it('renders variance badge with amber colour when |diff| > 10%', () => {
    render(
      <DetailFinance
        order={makeOrder({
          production_cost: 500,
          computed_production_cost: 600, // +20% vs manual
        })}
      />,
    )
    const badge = screen.getByTestId('variance-badge')
    expect(badge).toBeInTheDocument()
    expect(badge.textContent).toMatch(/\+20\.0% vs manual/)
    // Amber colour class applied for >10% divergence.
    expect(badge.className).toMatch(/amber/)
  })

  it('renders variance badge in neutral grey for 5–10% divergence', () => {
    render(
      <DetailFinance
        order={makeOrder({
          production_cost: 500,
          computed_production_cost: 540, // +8% — over 5%, under 10%
        })}
      />,
    )
    const badge = screen.getByTestId('variance-badge')
    expect(badge).toBeInTheDocument()
    expect(badge.className).not.toMatch(/amber/)
  })
})

describe('DetailFinance — FX-CONVERSION provenance', () => {
  it('explains a converted cost with its basis and rate', () => {
    // A USD order whose materials are priced in UAH: 500 UAH / 41.5 = 12.05.
    render(
      <DetailFinance
        order={makeOrder({
          currency: 'USD',
          total_price: 60,
          computed_production_cost: 12.05,
          cogs_fx_rate: 41.5,
          cogs_basis_amount: 500,
          cogs_basis_currency: 'UAH',
        })}
      />,
    )
    const note = screen.getByTestId('fx-provenance')
    expect(note).toHaveTextContent('500.00 UAH')
    expect(note).toHaveTextContent('41.5 UAH per $1')
    // The operator must know the number is frozen, not live.
    expect(note).toHaveTextContent('fixed when this order shipped')
  })

  it('shows no FX note for a same-currency order', () => {
    // KoraKlenu: UAH materials in a UAH order — no conversion happened, so a
    // rate line would be a fiction.
    render(
      <DetailFinance
        order={makeOrder({
          currency: 'UAH',
          computed_production_cost: 500,
          cogs_fx_rate: null,
        })}
      />,
    )
    expect(screen.queryByTestId('fx-provenance')).toBeNull()
  })

  it('shows no FX note when no cost was booked', () => {
    render(
      <DetailFinance
        order={makeOrder({ computed_production_cost: null, cogs_fx_rate: 41.5 })}
      />,
    )
    expect(screen.queryByTestId('fx-provenance')).toBeNull()
  })
})
