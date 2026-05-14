import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import OverheadMaterialsPage from '../OverheadMaterialsPage'

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
  useOverheadMaterials: () => ({
    data: [
      {
        id: 'oh-1',
        name: 'Нитка бавовняна чорна',
        unit: 'spool',
        notes: null,
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ],
    isLoading: false,
  }),
  useCreateOverheadMaterial: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateOverheadMaterial: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSoftDeleteOverheadMaterial: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

describe('OverheadMaterialsPage', () => {
  it('renders overhead materials returned by the hook', () => {
    render(
      <MemoryRouter>
        <OverheadMaterialsPage />
      </MemoryRouter>,
    )
    expect(screen.getByText('Нитка бавовняна чорна')).toBeInTheDocument()
    expect(screen.getByText('spool')).toBeInTheDocument()
  })
})
