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
    // ORDER-SHIPPING-1: null by default = an order no channel reported these
    // for, which is the derived-fallback path.
    shipping_revenue: null,
    discount_total: null,
    tax_total: null,
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

describe('DetailFinance — SHOP-FEE-1 platform fee', () => {
  it('subtracts the platform fee from net profit', () => {
    // 1000 total − 300 cost − 65 fee = 635. Without the fee term this card read
    // 700 while the finance page read 635 — the divergence this closes.
    render(
      <DetailFinance
        order={makeOrder({ production_cost: 300, platform_fee: 65 })}
      />,
    )
    expect(screen.getByText('Platform fee')).toBeInTheDocument()
    expect(screen.getByText('635.00')).toBeInTheDocument()
    expect(screen.queryByText('700.00')).toBeNull()
  })

  it('omits the fee row when no fee is set', () => {
    render(<DetailFinance order={makeOrder({ production_cost: 300 })} />)
    expect(screen.queryByText('Platform fee')).toBeNull()
    // Unchanged from before fees existed: 1000 − 300.
    expect(screen.getByText('700.00')).toBeInTheDocument()
  })

  it('treats a censored fee as zero rather than breaking net profit', () => {
    // A caller without VIEW_COSTS gets platform_fee: null (null-in-200), which
    // must degrade to the pre-fee arithmetic, not to NaN.
    render(
      <DetailFinance
        order={makeOrder({ production_cost: 300, platform_fee: null })}
      />,
    )
    expect(screen.getByText('700.00')).toBeInTheDocument()
  })
})

describe('DetailFinance — ORDER-SHIPPING-1 captured figures', () => {
  // The reported bug, verbatim. Order 91890_1841 (Nina Robinson, Shopify
  // 7410546344092): one 44.99 item, a 4.49 discount, 9.00 shipping, 49.50 total.
  // The card used to show a single "Shipping / other" row of 4.51 — the residual
  // total − items, with the discount silently folded in.
  const order1841 = {
    currency: 'USD',
    total_price: 49.5,
    items: [
      { id: 'i1', order_id: 'order-1', title: 'Money Clip', quantity: 1, unit_price: 44.99, currency: 'USD' },
    ] as unknown as OrderDetail['items'],
    shipping_revenue: 9,
    discount_total: 4.49,
    tax_total: 0,
  }

  it('renders shipping as the captured 9.00, not the 4.51 residual', () => {
    render(<DetailFinance order={makeOrder(order1841)} />)
    expect(screen.getByTestId('shipping-row')).toHaveTextContent('9.00')
    expect(screen.queryByText('4.51')).toBeNull()
    expect(screen.queryByText('Shipping / other (derived)')).toBeNull()
  })

  it('shows the discount on its own row, as a negative', () => {
    render(<DetailFinance order={makeOrder(order1841)} />)
    expect(screen.getByTestId('discount-row')).toHaveTextContent('−4.49')
  })

  it('makes the rows add up to the order total', () => {
    // 44.99 items − 4.49 discount + 9.00 shipping + 0 tax = 49.50.
    render(<DetailFinance order={makeOrder(order1841)} />)
    expect(screen.getByText('44.99')).toBeInTheDocument()
    expect(screen.getByText('49.50')).toBeInTheDocument()
  })

  it('hides a zero discount and a zero tax but shows a zero shipping', () => {
    // Free shipping is a fact worth rendering; a 0 discount is noise, and the
    // arithmetic is identical without the row.
    render(
      <DetailFinance
        order={makeOrder({
          currency: 'USD',
          total_price: 26.99,
          shipping_revenue: 0,
          discount_total: 0,
          tax_total: 0,
        })}
      />,
    )
    expect(screen.getByTestId('shipping-row')).toHaveTextContent('0.00')
    expect(screen.queryByTestId('discount-row')).toBeNull()
    expect(screen.queryByTestId('tax-row')).toBeNull()
  })

  it('renders tax when the order carries one', () => {
    render(
      <DetailFinance
        order={makeOrder({
          currency: 'USD',
          total_price: 105.91,
          shipping_revenue: 9,
          discount_total: 44.99,
          tax_total: 6.93,
        })}
      />,
    )
    expect(screen.getByTestId('tax-row')).toHaveTextContent('6.93')
  })
})

describe('DetailFinance — ORDER-SHIPPING-1 derived fallback', () => {
  it('labels the residual as derived when no figures were captured', () => {
    // Etsy / manual / not-yet-backfilled: 1000 total − 200 items = 800, the old
    // number, but never under a bare "Shipping" heading.
    render(
      <DetailFinance
        order={makeOrder({
          items: [
            { id: 'i1', order_id: 'order-1', title: 'X', quantity: 1, unit_price: 200, currency: 'UAH' },
          ] as unknown as OrderDetail['items'],
        })}
      />,
    )
    expect(screen.getByText('Shipping / other (derived)')).toBeInTheDocument()
    expect(screen.getByTestId('derived-shipping-row')).toHaveTextContent('800.00')
    expect(screen.getByTestId('derived-note')).toHaveTextContent('Derived as total − items')
    expect(screen.queryByTestId('shipping-row')).toBeNull()
  })

  it('switches to captured mode when even one figure arrived', () => {
    // The three are written as a set, so a partial set means a short payload,
    // not an order without shipping — falling back would present a residual
    // computed against figures we already know are incomplete.
    render(<DetailFinance order={makeOrder({ tax_total: 2.5 })} />)
    expect(screen.queryByText('Shipping / other (derived)')).toBeNull()
    expect(screen.queryByTestId('derived-note')).toBeNull()
    expect(screen.getByTestId('tax-row')).toHaveTextContent('2.50')
  })

  it('does not claim a present total is missing when items exceed it', () => {
    // Order 91890_1072: total 26.99, one 29.99 item → residual −3.00. The old
    // tooltip read "Order total not set", which was simply false.
    render(
      <DetailFinance
        order={makeOrder({
          currency: 'USD',
          total_price: 26.99,
          items: [
            { id: 'i1', order_id: 'order-1', title: 'Bat ID Card Cover', quantity: 1, unit_price: 29.99, currency: 'USD' },
          ] as unknown as OrderDetail['items'],
        })}
      />,
    )
    const dash = screen.getByTitle(
      'Line items exceed the order total — no shipping can be derived',
    )
    expect(dash).toBeInTheDocument()
    expect(screen.queryByTitle('Order total not set — shipping cannot be derived')).toBeNull()
  })

  it('still says the total is missing when it actually is', () => {
    render(<DetailFinance order={makeOrder({ total_price: 0 })} />)
    expect(
      screen.getByTitle('Order total not set — shipping cannot be derived'),
    ).toBeInTheDocument()
  })
})
