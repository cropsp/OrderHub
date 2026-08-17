import React from 'react'
import { render, screen } from '@testing-library/react'

import MaterialReceiptModal from '../MaterialReceiptModal'
import OverheadMaterialFormModal from '../OverheadMaterialFormModal'
import OverheadMaterialReceiptModal from '../OverheadMaterialReceiptModal'
import PackagingForm from '../PackagingForm'
import type { Material, OverheadMaterial } from '@/types/inventory'

vi.mock('@/hooks/useShops', () => ({
  useShops: () => ({ data: [] }),
}))

/**
 * MAT-UI-2 structural invariant. A submit button inside the scrollable region
 * can be scrolled out of reach; one outside it is pinned and always clickable.
 * jsdom cannot measure geometry, but it can prove the shape — and the shape is
 * what makes the geometry impossible to break.
 */
function assertSubmitIsPinned(submitLabel: RegExp) {
  const content = document.querySelector('[data-slot=dialog-content]')
  expect(content).not.toBeNull()

  const scroller = content!.querySelector('.overflow-y-auto')
  expect(scroller).not.toBeNull()

  const submit = screen.getByRole('button', { name: submitLabel })
  const header = content!.querySelector('[data-slot=dialog-header]')

  expect(scroller!.contains(submit)).toBe(false)
  expect(scroller!.contains(header)).toBe(false)
}

const material: Material = {
  id: 'mat-1',
  name: 'Шкіра італійська чорна',
  unit: 'dm2',
  currency: 'UAH',
  current_unit_cost: '0',
  stock_quantity: '0',
  low_stock_threshold: '0',
  waste_percent: '0',
  supplier_name: null,
  notes: null,
  is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

const overhead: OverheadMaterial = {
  id: 'oh-1',
  name: 'Скотч пакувальний',
  unit: 'шт',
  notes: null,
  is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

describe('dialog layout — submit button stays outside the scroll container', () => {
  it('PackagingForm', () => {
    render(<PackagingForm isOpen onClose={vi.fn()} onSave={vi.fn()} />)

    assertSubmitIsPinned(/Save Packaging/i)
  })

  it('MaterialReceiptModal', () => {
    render(
      <MaterialReceiptModal
        isOpen
        onClose={vi.fn()}
        material={material}
        onSubmit={vi.fn()}
      />,
    )

    assertSubmitIsPinned(/Register Receipt/i)
  })

  it('OverheadMaterialFormModal', () => {
    render(<OverheadMaterialFormModal isOpen onClose={vi.fn()} onSave={vi.fn()} />)

    assertSubmitIsPinned(/^Create$/i)
  })

  it('OverheadMaterialReceiptModal', () => {
    render(
      <OverheadMaterialReceiptModal
        isOpen
        onClose={vi.fn()}
        overhead={overhead}
        onSubmit={vi.fn()}
      />,
    )

    assertSubmitIsPinned(/Save Expense/i)
  })
})
