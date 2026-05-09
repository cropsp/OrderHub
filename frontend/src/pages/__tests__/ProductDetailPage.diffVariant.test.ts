import { describe, expect, it } from 'vitest'

import { diffVariant, validateNewVariant, type VariantDraft } from '../ProductDetailPage'
import type { ProductVariant } from '@/types/inventory'

function makeOriginal(overrides: Partial<ProductVariant> = {}): ProductVariant {
  return {
    id: 'var-1',
    product_id: 'prod-1',
    sku: 'SKU-1',
    variant_name: 'Brown',
    weight_g: 0,
    length_mm: 0,
    width_mm: 0,
    height_mm: 0,
    price: null,
    cost_price: null,
    stock_quantity: 0,
    is_active: true,
    ...overrides,
  }
}

function makeDraft(overrides: Partial<VariantDraft> = {}): VariantDraft {
  return {
    _key: 'var-1',
    id: 'var-1',
    sku: 'SKU-1',
    variant_name: 'Brown',
    weight_g: '0',
    length_mm: '0',
    width_mm: '0',
    height_mm: '0',
    price: '',
    cost_price: '',
    stock_quantity: '0',
    ...overrides,
  }
}

describe('diffVariant', () => {
  it('returns null for an untouched IMP-1 sentinel variant (all zeros)', () => {
    // BUG-7 regression guard: zero-dim sentinel rows must NOT register as
    // dirty when the user has not changed anything.
    const original = makeOriginal()
    const draft = makeDraft()
    expect(diffVariant(draft, original)).toBeNull()
  })

  it('returns only { id, weight_g } when weight_g changes 0 → 120 on an IMP-1 row', () => {
    const original = makeOriginal()
    const draft = makeDraft({ weight_g: '120' })
    expect(diffVariant(draft, original)).toEqual({ id: 'var-1', weight_g: 120 })
  })

  it('returns { id, cost_price: null } when the user clears a cost_price', () => {
    // Q3 regression guard: clearing a previously-set decimal field must
    // surface as an explicit clear-to-null in the patch.
    const original = makeOriginal({ cost_price: 50 })
    const draft = makeDraft({ cost_price: '' })
    expect(diffVariant(draft, original)).toEqual({ id: 'var-1', cost_price: null })
  })

  it('treats price "130.00" === "130" as unchanged (KoraKlenu regression)', () => {
    const original = makeOriginal({ price: '130.00' })
    const draft = makeDraft({ price: '130' })
    expect(diffVariant(draft, original)).toBeNull()
  })

  it('normalizes empty-string ↔ null for sku', () => {
    const originalNullSku = makeOriginal({ sku: null })
    const draftEmptySku = makeDraft({ sku: '' })
    expect(diffVariant(draftEmptySku, originalNullSku)).toBeNull()

    const originalWithSku = makeOriginal({ sku: 'A' })
    const draftClearedSku = makeDraft({ sku: '' })
    expect(diffVariant(draftClearedSku, originalWithSku)).toEqual({
      id: 'var-1',
      sku: null,
    })
  })

  it('returns price as a number when set from null', () => {
    const original = makeOriginal({ cost_price: null })
    const draft = makeDraft({ cost_price: '25.5' })
    expect(diffVariant(draft, original)).toEqual({ id: 'var-1', cost_price: 25.5 })
  })

  it('detects only the touched field when KoraKlenu price 130.00 → 135.00', () => {
    const original = makeOriginal({
      sku: 'KORA-BROWN',
      variant_name: 'Brown',
      weight_g: 200,
      length_mm: 80,
      width_mm: 60,
      height_mm: 30,
      price: '130.00',
      cost_price: '50.00',
      stock_quantity: 10,
    })
    const draft = makeDraft({
      sku: 'KORA-BROWN',
      variant_name: 'Brown',
      weight_g: '200',
      length_mm: '80',
      width_mm: '60',
      height_mm: '30',
      price: '135.00',
      cost_price: '50.00',
      stock_quantity: '10',
    })
    expect(diffVariant(draft, original)).toEqual({ id: 'var-1', price: 135 })
  })
})

describe('validateNewVariant', () => {
  // Add Variant regression: new variants must still require all four dims to
  // be positive integers, even after the diff-based path relaxes that for
  // existing variants.
  it('rejects a new variant with weight_g = 0', () => {
    const draft = makeDraft({
      id: undefined,
      _key: 'new-1',
      sku: 'NEW-1',
      variant_name: 'New',
      weight_g: '0',
      length_mm: '10',
      width_mm: '10',
      height_mm: '10',
      price: '5.00',
    })
    expect(validateNewVariant(draft)).toBe(
      'Each variant needs positive integer weight and dimensions',
    )
  })

  it('accepts a new variant with all four dims positive integers', () => {
    const draft = makeDraft({
      id: undefined,
      _key: 'new-2',
      sku: 'NEW-2',
      variant_name: 'New',
      weight_g: '120',
      length_mm: '50',
      width_mm: '40',
      height_mm: '20',
      price: '10.00',
    })
    expect(validateNewVariant(draft)).toBeNull()
  })
})
