import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import MaterialsPage from '../MaterialsPage'

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

const useMaterialsMock = vi.fn(() => ({
  data: [
    {
      id: 'mat-1',
      name: 'Шкіра італійська чорна',
      unit: 'dm2',
      currency: 'UAH',
      current_unit_cost: '0',
      stock_quantity: '0',
      low_stock_threshold: '0',
      waste_percent: '0',
      supplier_name: 'Conceria Walpier',
      notes: null,
      is_active: true,
      category: 'MATERIAL',
      is_stock_tracked: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ],
  isLoading: false,
}))

vi.mock('@/hooks/useMaterials', () => ({
  useMaterials: (filters: unknown) => useMaterialsMock(filters as never),
  useCreateMaterial: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateMaterial: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSoftDeleteMaterial: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

describe('MaterialsPage', () => {
  beforeEach(() => {
    useMaterialsMock.mockClear()
  })

  it('renders materials returned by the hook', () => {
    render(
      <MemoryRouter>
        <MaterialsPage />
      </MemoryRouter>,
    )
    expect(screen.getByText('Шкіра італійська чорна')).toBeInTheDocument()
    expect(screen.getByText('Conceria Walpier')).toBeInTheDocument()
  })

  it('"Show archived" toggle flips includeInactive arg passed to the hook', () => {
    render(
      <MemoryRouter>
        <MaterialsPage />
      </MemoryRouter>,
    )

    // First render: include_inactive=false
    expect(useMaterialsMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ includeInactive: false }),
    )

    const checkbox = screen.getByLabelText(/show archived/i)
    fireEvent.click(checkbox)

    expect(useMaterialsMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ includeInactive: true }),
    )
  })

  // WH-1 — every packaging box now has a Material behind it. Those belong to the
  // Packaging page, so they stay out of this list unless explicitly asked for.
  it('"Show packaging" toggle flips the category filter passed to the hook', () => {
    render(
      <MemoryRouter>
        <MaterialsPage />
      </MemoryRouter>,
    )

    expect(useMaterialsMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ category: 'MATERIAL' }),
    )

    fireEvent.click(screen.getByLabelText(/show packaging/i))

    // undefined = no category filter = both kinds.
    expect(useMaterialsMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ category: undefined }),
    )
  })

  it('"New Material" button opens the create modal', () => {
    render(
      <MemoryRouter>
        <MaterialsPage />
      </MemoryRouter>,
    )

    // Modal title not present before opening.
    expect(screen.queryByText('Register New Material')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /new material/i }))

    expect(screen.getByText('Register New Material')).toBeInTheDocument()
  })
})
