import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import MaterialFormModal from '../MaterialFormModal'
import type { Material } from '@/types/inventory'

// WH-1: the form's job for is_stock_tracked is to send it on BOTH paths — create
// and update build separate payload literals, so each needs its own guard.

const trackedMaterial: Material = {
  id: 'mat-1',
  name: 'Шкіра італійська чорна',
  unit: 'dm2',
  currency: 'UAH',
  current_unit_cost: '597.14',
  stock_quantity: '33',
  low_stock_threshold: '0',
  waste_percent: '0',
  supplier_name: null,
  supplier_sku: null,
  notes: null,
  is_active: true,
  category: 'MATERIAL',
  is_stock_tracked: true,
  created_at: '2026-05-14T10:00:00Z',
  updated_at: '2026-05-14T10:00:00Z',
}

const serviceMaterial: Material = {
  ...trackedMaterial,
  id: 'mat-2',
  name: 'Лазерна порізка',
  is_stock_tracked: false,
}

function setup(initialData: Material | null = null) {
  const onSave = vi.fn().mockResolvedValue(undefined)
  render(
    <MaterialFormModal
      isOpen
      onClose={vi.fn()}
      onSave={onSave}
      initialData={initialData}
    />,
  )
  return onSave
}

describe('MaterialFormModal — stock tracking', () => {
  it('sends is_stock_tracked=false on create when the box is ticked', async () => {
    const onSave = setup()

    fireEvent.change(screen.getByPlaceholderText(/Шкіра італійська чорна/i), {
      target: { value: 'Пошиття' },
    })
    fireEvent.click(screen.getByLabelText(/does not consume stock/i))
    fireEvent.click(screen.getByRole('button', { name: /Create Material/i }))

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
    expect(onSave.mock.calls[0][0]).toMatchObject({
      name: 'Пошиття',
      is_stock_tracked: false,
    })
  })

  it('defaults a new material to stock-tracked', async () => {
    const onSave = setup()

    fireEvent.change(screen.getByPlaceholderText(/Шкіра італійська чорна/i), {
      target: { value: 'Нитка' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Create Material/i }))

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
    expect(onSave.mock.calls[0][0]).toMatchObject({ is_stock_tracked: true })
  })

  it('reflects an existing untracked material and sends it back on update', async () => {
    const onSave = setup(serviceMaterial)

    const checkbox = screen.getByLabelText(/does not consume stock/i) as HTMLInputElement
    expect(checkbox.checked).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: /Save Changes/i }))

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
    expect(onSave.mock.calls[0][0]).toMatchObject({ is_stock_tracked: false })
  })

  it('leaves a tracked material tracked when editing', async () => {
    const onSave = setup(trackedMaterial)

    const checkbox = screen.getByLabelText(/does not consume stock/i) as HTMLInputElement
    expect(checkbox.checked).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: /Save Changes/i }))

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
    expect(onSave.mock.calls[0][0]).toMatchObject({ is_stock_tracked: true })
  })

  it('offers no category control — packaging materials are owned by the packaging page', () => {
    setup(trackedMaterial)
    expect(screen.queryByText(/packaging/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/category/i)).not.toBeInTheDocument()
  })
})
