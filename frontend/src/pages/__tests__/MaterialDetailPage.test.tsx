import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import MaterialDetailPage from '../MaterialDetailPage'

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: {
      id: 'user-1',
      email: 'owner@orderhub.dev',
      full_name: 'Owner',
      role: 'owner',
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    isLoading: false,
    isAuthenticated: true,
    logout: vi.fn(),
    login: vi.fn(),
  }),
}))

vi.mock('@/hooks/useShops', () => ({
  useShops: () => ({ data: [], isLoading: false }),
}))

const baseMaterial = {
  id: 'mat-1',
  name: 'Шкіра італійська чорна',
  unit: 'dm2',
  currency: 'UAH',
  current_unit_cost: '588.0000',
  stock_quantity: '25.00',
  low_stock_threshold: '0.00',
  waste_percent: '0.00',
  supplier_name: 'Conceria Walpier',
  notes: null,
  is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

const materialMock = { data: baseMaterial, isLoading: false }

vi.mock('@/hooks/useMaterials', () => ({
  useMaterial: () => materialMock,
  useMaterialReceipts: () => ({ data: [] }),
  useMaterialMovements: () => ({ data: [] }),
  useCreateMaterialReceipt: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAdjustMaterialStock: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateMaterial: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/inventory/materials/mat-1']}>
      <Routes>
        <Route path="/inventory/materials/:id" element={<MaterialDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('MaterialDetailPage', () => {
  beforeEach(() => {
    materialMock.data = baseMaterial
  })

  it('renders the stock summary with current quantity and unit', () => {
    renderPage()
    expect(screen.getAllByText('Шкіра італійська чорна').length).toBeGreaterThan(0)
    expect(screen.getByText('25.00 dm2')).toBeInTheDocument()
    expect(screen.getByText('588.00 UAH/dm2')).toBeInTheDocument()
  })

  it('clicking "Receipt" opens the receipt modal', () => {
    renderPage()
    // Modal dialog absent before clicking.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    const buttons = screen.getAllByRole('button', { name: /Receipt/i })
    fireEvent.click(buttons[0])
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    // The modal description references the material name in the receipt copy.
    expect(
      screen.getByText(/weighted-average cost will recompute/i),
    ).toBeInTheDocument()
  })

  it('renders LOW badge when stock_quantity <= low_stock_threshold (and threshold > 0)', () => {
    materialMock.data = {
      ...baseMaterial,
      stock_quantity: '5.00',
      low_stock_threshold: '10.00',
    }
    renderPage()
    expect(screen.getByText('Low')).toBeInTheDocument()
  })
})
