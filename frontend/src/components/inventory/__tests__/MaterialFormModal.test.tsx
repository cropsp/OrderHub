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
  const onClose = vi.fn()
  const { rerender } = render(
    <MaterialFormModal
      isOpen
      onClose={onClose}
      onSave={onSave}
      initialData={initialData}
    />,
  )
  // Re-render with a different `initialData` and nothing else changed — the seam
  // where a background refetch replaces the object the modal was opened with.
  const rerenderWith = (next: Material | null) =>
    rerender(
      <MaterialFormModal
        isOpen
        onClose={onClose}
        onSave={onSave}
        initialData={next}
      />,
    )
  return { onSave, rerenderWith }
}

function stockCheckbox() {
  return screen.getByLabelText(/does not consume stock/i) as HTMLInputElement
}

describe('MaterialFormModal — stock tracking', () => {
  it('sends is_stock_tracked=false on create when the box is ticked', async () => {
    const { onSave } = setup()

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
    const { onSave } = setup()

    fireEvent.change(screen.getByPlaceholderText(/Шкіра італійська чорна/i), {
      target: { value: 'Нитка' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Create Material/i }))

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
    expect(onSave.mock.calls[0][0]).toMatchObject({ is_stock_tracked: true })
  })

  it('reflects an existing untracked material and sends it back on update', async () => {
    const { onSave } = setup(serviceMaterial)

    expect(stockCheckbox().checked).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: /Save Changes/i }))

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
    expect(onSave.mock.calls[0][0]).toMatchObject({ is_stock_tracked: false })
  })

  it('leaves a tracked material tracked when editing', async () => {
    const { onSave } = setup(trackedMaterial)

    expect(stockCheckbox().checked).toBe(false)

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

// MAT-UI-1. The seam no other case covers: the modal is open with edits in it and
// the parent hands down a *new* `initialData` object. On the detail page that is a
// React Query refetch — a receipt or a stock adjustment invalidates ['materials', id]
// and the resolved data arrives as a fresh reference. Keying the reset on that
// reference silently threw the user's typing away and then saved the server's values
// back, with no error and a closed modal. The reset must key on the target's id.
describe('MaterialFormModal — in-progress edits survive a refetch', () => {
  it('keeps the ticked flag when initialData is replaced by an identical object', async () => {
    const { onSave, rerenderWith } = setup(trackedMaterial)

    fireEvent.click(stockCheckbox())
    rerenderWith({ ...trackedMaterial })

    expect(stockCheckbox().checked).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: /Save Changes/i }))

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
    expect(onSave.mock.calls[0][0]).toMatchObject({ is_stock_tracked: false })
  })

  it('keeps typed text when initialData is replaced by an identical object', async () => {
    const { onSave, rerenderWith } = setup(trackedMaterial)

    fireEvent.change(screen.getByPlaceholderText(/Grade, color descriptors/i), {
      target: { value: 'Партія 2026-08' },
    })
    rerenderWith({ ...trackedMaterial })

    fireEvent.click(screen.getByRole('button', { name: /Save Changes/i }))

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
    expect(onSave.mock.calls[0][0]).toMatchObject({ notes: 'Партія 2026-08' })
  })

  it('still re-syncs when the target material changes', () => {
    const { rerenderWith } = setup(trackedMaterial)
    expect(stockCheckbox().checked).toBe(false)

    // Different id — a different row, not a refetch of the same one.
    rerenderWith(serviceMaterial)

    expect(stockCheckbox().checked).toBe(true)
  })
})

// WH-1-followup-1: the piece unit.
describe('unit options', () => {
  it('offers шт, the canonical piece unit for this business', () => {
    setup()

    const unitSelect = screen.getByDisplayValue('dm2')
    const options = Array.from(unitSelect.querySelectorAll('option')).map(
      o => o.textContent,
    )

    expect(options).toContain('шт')
    // 'pcs' stays for the rows already on it — the follow-up deliberately does
    // not migrate them, and removing the option would strand those materials on
    // a value their own form could not display.
    expect(options).toContain('pcs')
  })
})
