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
  material_is_active: false,
  line_cost: '0.00',
}

const mutateAsync = vi.fn().mockResolvedValue(undefined)

vi.mock('@/hooks/useBom', () => ({
  useBom: vi.fn(),
  useBomCost: () => ({ data: [], refetch: vi.fn(), isFetching: false }),
  useReplaceBom: () => ({ mutateAsync, isPending: false }),
}))

vi.mock('@/hooks/useMaterials', () => ({
  useMaterials: () => ({ data: [material1, material2] }),
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
})
