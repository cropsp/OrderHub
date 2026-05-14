import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import MaterialReceiptModal from '../MaterialReceiptModal'
import type { Material } from '@/types/inventory'

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

describe('MaterialReceiptModal', () => {
  it('submitting with valid payload invokes onSubmit with the right shape', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const onClose = vi.fn()

    render(
      <MaterialReceiptModal
        isOpen={true}
        onClose={onClose}
        material={material}
        onSubmit={onSubmit}
      />,
    )

    fireEvent.change(screen.getByPlaceholderText('e.g. 25'), {
      target: { value: '25' },
    })
    fireEvent.change(screen.getByPlaceholderText('e.g. 580'), {
      target: { value: '580' },
    })
    // Shipping has placeholder "0" — leave empty to test optional path.

    fireEvent.click(screen.getByRole('button', { name: /Register Receipt/i }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    const payload = onSubmit.mock.calls[0][0]
    expect(payload.qty).toBe(25)
    expect(payload.unit_cost).toBe(580)
    expect(payload.currency).toBe('UAH')
    expect(payload.shipping_cost).toBeNull()
  })

  it('currency input is disabled (locked to material currency)', () => {
    render(
      <MaterialReceiptModal
        isOpen={true}
        onClose={vi.fn()}
        material={material}
        onSubmit={vi.fn()}
      />,
    )
    const currencyInputs = screen
      .getAllByDisplayValue('UAH')
      .filter((el) => (el as HTMLInputElement).tagName === 'INPUT')
    expect(currencyInputs.length).toBeGreaterThan(0)
    expect(currencyInputs[0]).toBeDisabled()
  })
})
