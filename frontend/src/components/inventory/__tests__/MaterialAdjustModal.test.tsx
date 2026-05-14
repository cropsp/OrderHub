import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import MaterialAdjustModal from '../MaterialAdjustModal'
import type { Material } from '@/types/inventory'

// Radix Select calls scrollIntoView on focused option, which jsdom lacks.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

const material: Material = {
  id: 'mat-1',
  name: 'Шкіра',
  unit: 'dm2',
  currency: 'UAH',
  current_unit_cost: '597',
  stock_quantity: '35',
  low_stock_threshold: '0',
  waste_percent: '0',
  supplier_name: null,
  notes: null,
  is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

describe('MaterialAdjustModal', () => {
  it('submitting with reason=waste and a negative delta calls onSubmit with the correct payload', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <MaterialAdjustModal
        isOpen={true}
        onClose={vi.fn()}
        material={material}
        onSubmit={onSubmit}
      />,
    )

    fireEvent.change(screen.getByPlaceholderText('-3 or +5'), {
      target: { value: '-2' },
    })
    // Default reason is 'adjustment' — change to 'waste'.
    fireEvent.click(screen.getByRole('combobox'))
    const wasteOption = await screen.findByRole('option', { name: /waste/i })
    fireEvent.click(wasteOption)

    fireEvent.change(screen.getByPlaceholderText(/Cut error/i), {
      target: { value: 'Cut error' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Save Adjustment/i }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    const payload = onSubmit.mock.calls[0][0]
    expect(payload.delta).toBe(-2)
    expect(payload.reason).toBe('waste')
    expect(payload.notes).toBe('Cut error')
  })
})
