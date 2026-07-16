import { describe, it, expect } from 'vitest'

import { orderDisplayName } from '../orderName'

describe('orderDisplayName', () => {
  it('prefers the recipient (shipping_name) when present', () => {
    expect(
      orderDisplayName({ shipping_name: 'Paula Borowsky', customer_name: 'E B (qzp7sdny)' }),
    ).toBe('Paula Borowsky')
  })

  it('falls back to customer_name when shipping_name is whitespace-only', () => {
    expect(
      orderDisplayName({ shipping_name: '   ', customer_name: 'Jane Doe' }),
    ).toBe('Jane Doe')
  })

  it('falls back to customer_name when shipping_name is null', () => {
    expect(
      orderDisplayName({ shipping_name: null, customer_name: 'Jane Doe' }),
    ).toBe('Jane Doe')
  })

  it('returns "Unknown" when both are empty or null', () => {
    expect(orderDisplayName({ shipping_name: '', customer_name: '' })).toBe('Unknown')
    expect(orderDisplayName({ shipping_name: null, customer_name: null })).toBe('Unknown')
    expect(orderDisplayName({ shipping_name: '  ', customer_name: '  ' })).toBe('Unknown')
  })
})
