import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import BomEditor from '../BomEditor'
import type { BomItem, BomReadResponse, Material } from '@/types/inventory'

const material1: Material = {
  id: 'mat-1',
  name: 'Шкіра італійська чорна',
  unit: 'dm2',
  currency: 'UAH',
  current_unit_cost: '597.14',
  stock_quantity: '33',
  low_stock_threshold: '0',
  waste_percent: '0',
  supplier_name: null,
  notes: null,
  is_active: true,
  created_at: '2026-05-14T10:00:00Z',
  updated_at: '2026-05-14T10:00:00Z',
}

const material2: Material = {
  id: 'mat-2',
  name: 'Brass zipper 18cm',
  unit: 'pcs',
  currency: 'UAH',
  current_unit_cost: '45.00',
  stock_quantity: '120',
  low_stock_threshold: '0',
  waste_percent: '0',
  supplier_name: null,
  notes: null,
  is_active: true,
  created_at: '2026-05-14T10:00:00Z',
  updated_at: '2026-05-14T10:00:00Z',
}

const bomItem1: BomItem = {
  id: 'bom-1',
  product_id: 'prod-1',
  material_id: 'mat-1',
  qty_per_unit: '5.00',
  notes: null,
  material_name: material1.name,
  material_unit: material1.unit,
  material_currency: material1.currency,
  material_current_unit_cost: material1.current_unit_cost,
  material_waste_percent: material1.waste_percent,
  material_is_active: true,
  line_cost: '2985.70',
}

const bomItemInactive: BomItem = {
  id: 'bom-2',
  product_id: 'prod-1',
  material_id: 'mat-archived',
  qty_per_unit: '0.50',
  notes: null,
  material_name: 'Фанера 4mm',
  material_unit: 'm2',
  material_currency: 'UAH',
  material_current_unit_cost: '0',
  material_waste_percent: '0',
  material_is_active: false,
  line_cost: '0.00',
}

// BOM-WASTE-1 fixture: a material that actually carries a waste allowance.
const material3: Material = {
  id: 'mat-3',
  name: 'Шкіра Crazy Horse',
  unit: 'dm2',
  currency: 'UAH',
  current_unit_cost: '580.00',
  stock_quantity: '80',
  low_stock_threshold: '0',
  waste_percent: '15',
  supplier_name: null,
  notes: null,
  is_active: true,
  created_at: '2026-05-14T10:00:00Z',
  updated_at: '2026-05-14T10:00:00Z',
}

const bomItemWaste: BomItem = {
  id: 'bom-3',
  product_id: 'prod-1',
  material_id: 'mat-3',
  qty_per_unit: '0.13',
  notes: null,
  material_name: material3.name,
  material_unit: material3.unit,
  material_currency: material3.currency,
  material_current_unit_cost: material3.current_unit_cost,
  material_waste_percent: material3.waste_percent,
  material_is_active: true,
  line_cost: '86.71',
}

// A discontinued material carrying waste — absent from the picker, so the
// editor must price it from `fallback` (the reason material_waste_percent is
// on BomItemRead at all).
const bomItemInactiveWaste: BomItem = {
  id: 'bom-4',
  product_id: 'prod-1',
  material_id: 'mat-archived-2',
  qty_per_unit: '2.00',
  notes: null,
  material_name: 'Нитка вощена (знято з виробництва)',
  material_unit: 'm',
  material_currency: 'UAH',
  material_current_unit_cost: '100.00',
  material_waste_percent: '20',
  material_is_active: false,
  line_cost: '240.00',
}

const mutateAsync = vi.fn().mockResolvedValue(undefined)

vi.mock('@/hooks/useBom', () => ({
  useBom: vi.fn(),
  useBomCost: () => ({ data: [], refetch: vi.fn(), isFetching: false }),
  useReplaceBom: () => ({ mutateAsync, isPending: false }),
}))

vi.mock('@/hooks/useMaterials', () => ({
  useMaterials: () => ({ data: [material1, material2, material3] }),
}))

import { useBom } from '@/hooks/useBom'
const useBomMock = useBom as unknown as ReturnType<typeof vi.fn>

function bomResponse(items: BomItem[]): BomReadResponse {
  return {
    items,
    cost: [{ currency: 'UAH', amount: '0.00' }],
    has_inactive_material: items.some((it) => !it.material_is_active),
  }
}

beforeEach(() => {
  mutateAsync.mockClear()
})

describe('BomEditor', () => {
  it('renders existing BomItems from mocked hook response', () => {
    useBomMock.mockReturnValue({ data: bomResponse([bomItem1]), isLoading: false })
    render(<BomEditor productId="prod-1" />)
    // The material picker pre-selects the existing material; its name appears
    // in the active options too.
    expect(screen.getAllByText(material1.name).length).toBeGreaterThan(0)
    expect(screen.getByDisplayValue('5.00')).toBeInTheDocument()
  })

  it('"+ Add Material" appends an empty editable row', () => {
    useBomMock.mockReturnValue({ data: bomResponse([]), isLoading: false })
    render(<BomEditor productId="prod-1" />)
    // Empty state shows the CTA — clicking it adds the first row.
    fireEvent.click(screen.getByRole('button', { name: /Add Material/i }))
    // The new row's material picker is the placeholder option.
    expect(screen.getByText('— pick a material —')).toBeInTheDocument()
  })

  it('Save calls useReplaceBom with current items', async () => {
    useBomMock.mockReturnValue({ data: bomResponse([bomItem1]), isLoading: false })
    render(<BomEditor productId="prod-1" />)
    // Mutate qty so the form becomes dirty.
    fireEvent.change(screen.getByDisplayValue('5.00'), { target: { value: '6' } })
    fireEvent.click(screen.getByRole('button', { name: /Save Recipe/i }))
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1))
    const payload = mutateAsync.mock.calls[0][0]
    expect(payload).toHaveLength(1)
    expect(payload[0]).toMatchObject({ material_id: 'mat-1', qty_per_unit: '6' })
  })

  it('renders the Discontinued badge when a row references an inactive material', () => {
    useBomMock.mockReturnValue({
      data: bomResponse([bomItemInactive]),
      isLoading: false,
    })
    render(<BomEditor productId="prod-1" />)
    expect(screen.getByTestId('discontinued-badge')).toBeInTheDocument()
    // Recipe-level banner should also surface.
    expect(
      screen.getByText(/references one or more discontinued materials/i),
    ).toBeInTheDocument()
  })

  // BOM-WASTE-1 — the editor computes its own line cost and recipe total in JS
  // (the server's compute_bom_cost never reaches this screen), so waste has to
  // be applied here too or the reviewed number diverges from booked COGS.
  it('line cost and recipe total include the material waste allowance', () => {
    useBomMock.mockReturnValue({
      data: bomResponse([bomItemWaste]),
      isLoading: false,
    })
    render(<BomEditor productId="prod-1" />)

    // 0.13 × 1.15 × 580.00 = 86.71 — shown in the Line cost cell and the total.
    expect(screen.getAllByText('86.71 UAH').length).toBeGreaterThan(0)
    // The waste-free number (0.13 × 580.00) must not appear anywhere.
    expect(screen.queryByText('75.40 UAH')).not.toBeInTheDocument()
  })

  it('applies waste from the fallback when the material is discontinued', () => {
    useBomMock.mockReturnValue({
      data: bomResponse([bomItemInactiveWaste]),
      isLoading: false,
    })
    render(<BomEditor productId="prod-1" />)

    // mat-archived-2 is absent from useMaterials, so this exercises `fallback`.
    // 2.00 × 1.20 × 100.00 = 240.00, not the waste-free 200.00.
    expect(screen.getAllByText('240.00 UAH').length).toBeGreaterThan(0)
    expect(screen.queryByText('200.00 UAH')).not.toBeInTheDocument()
  })
})
