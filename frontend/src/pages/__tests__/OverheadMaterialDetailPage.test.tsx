import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import OverheadMaterialDetailPage from '../OverheadMaterialDetailPage'

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

vi.mock('@/hooks/useOverheadMaterials', () => ({
  useOverheadMaterial: () => ({
    data: {
      id: 'oh-1',
      name: 'Клей PVA',
      unit: 'ml',
      notes: null,
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    isLoading: false,
  }),
  useOverheadMaterialReceipts: () => ({
    data: [
      {
        id: 'rcpt-1',
        overhead_material_id: 'oh-1',
        shop_id: null,
        shop_name: null,
        qty: '3.00',
        total_cost: '450.00',
        currency: 'UAH',
        supplier: 'ATB',
        invoice_no: 'INV-OH-1',
        received_at: new Date().toISOString(),
        notes: null,
        user_id: 'user-1',
        created_at: new Date().toISOString(),
      },
    ],
  }),
  useCreateOverheadMaterialReceipt: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}))

describe('OverheadMaterialDetailPage', () => {
  it('renders the page with the receipts table containing the seeded row', () => {
    render(
      <MemoryRouter initialEntries={['/inventory/overhead-materials/oh-1']}>
        <Routes>
          <Route
            path="/inventory/overhead-materials/:id"
            element={<OverheadMaterialDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getAllByText('Клей PVA').length).toBeGreaterThan(0)
    expect(screen.getByText('ATB')).toBeInTheDocument()
    expect(screen.getByText(/Unallocated/i)).toBeInTheDocument()
    expect(screen.getByText('450.00')).toBeInTheDocument()
  })
})
