import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import PackagingPage from '../PackagingPage'

let currentUser: { role: string; capabilities?: string[] } = {
  role: 'owner',
  capabilities: ['view_finance', 'view_costs'],
}

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: {
      id: 'user-1',
      email: 'someone@orderhub.dev',
      full_name: 'Someone',
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      ...currentUser,
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

// The receipt modal reaches for the materials API through react-query; the page
// tests never open it, so a stub keeps the module graph flat.
vi.mock('@/components/inventory/PackagingReceiptModal', () => ({
  default: ({ box }: { box: { name: string } }) => (
    <div data-testid="receipt-modal">{box.name}</div>
  ),
}))

const box = (overrides: Record<string, unknown> = {}) => ({
  id: 'box-1',
  material_id: 'mat-1',
  name: 'Коробка 100×120×50',
  packaging_type: 'BOX',
  inner_length_mm: 100,
  inner_width_mm: 120,
  inner_height_mm: 50,
  max_thickness_mm: null,
  max_weight_g: 2000,
  tare_weight_g: 10,
  sort_order: 0,
  // WH-2: Decimal strings, exactly as the API serves them.
  stock_quantity: '10.00',
  low_stock_threshold: '5.00',
  material_is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})

const usePackagingMock = vi.fn(() => ({ data: [box()], isLoading: false }))
const archiveMutateAsync = vi.fn().mockResolvedValue(undefined)

vi.mock('@/hooks/usePackaging', () => ({
  usePackaging: (includeArchived: boolean) => usePackagingMock(includeArchived as never),
  useCreatePackaging: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdatePackaging: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeletePackaging: () => ({ mutateAsync: archiveMutateAsync, isPending: false }),
  useBulkImportPackaging: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

function renderPage() {
  return render(
    <MemoryRouter>
      <PackagingPage />
    </MemoryRouter>,
  )
}

describe('PackagingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentUser = { role: 'owner', capabilities: ['view_finance', 'view_costs'] }
    usePackagingMock.mockReturnValue({ data: [box()], isLoading: false })
  })

  it('does not flag a two-digit stock as low', () => {
    // The regression this exists for: WH-2 made both counters Decimal STRINGS,
    // and "10.00" <= "5.00" is true lexicographically. Comparing them raw would
    // put the Low badge on every box with double-digit stock — the healthy ones.
    renderPage()

    expect(screen.getByText('10')).toBeInTheDocument()
    expect(screen.queryByText('Low')).not.toBeInTheDocument()
  })

  it('flags stock at or below the threshold', () => {
    usePackagingMock.mockReturnValue({
      data: [box({ stock_quantity: '4.00', low_stock_threshold: '5.00' })],
      isLoading: false,
    })
    renderPage()

    expect(screen.getByText('Low')).toBeInTheDocument()
  })

  it('archives through a dialog rather than a native confirm', async () => {
    // WH-1-followup-1 banned native confirm(); WH-2 also made the action
    // non-destructive, so the copy has to say archive, not delete.
    renderPage()

    fireEvent.click(screen.getByTitle('Archive'))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/hidden from the packaging picker/i)).toBeInTheDocument()
    expect(archiveMutateAsync).not.toHaveBeenCalled()

    fireEvent.click(within(dialog).getByRole('button', { name: 'Archive' }))
    await waitFor(() =>
      expect(archiveMutateAsync).toHaveBeenCalledWith({ id: 'box-1' }),
    )
  })

  it('marks an archived box and disables archiving it again', () => {
    usePackagingMock.mockReturnValue({
      data: [box({ material_is_active: false })],
      isLoading: false,
    })
    renderPage()

    expect(screen.getByText('Archived')).toBeInTheDocument()
    expect(screen.getByTitle('Already archived')).toBeDisabled()
  })

  it('asks the API for archived boxes only when the filter is on', () => {
    renderPage()
    expect(usePackagingMock).toHaveBeenLastCalledWith(false)

    fireEvent.click(screen.getByLabelText(/show archived/i))
    expect(usePackagingMock).toHaveBeenLastCalledWith(true)
  })

  it('disables the receipt and history actions without view_costs', () => {
    // Both go through /api/materials, which is gated on the capability as a whole.
    // Disabling beats letting the click 403 — but the row must stay readable,
    // since the packaging list itself is open to any authenticated user.
    currentUser = { role: 'manager', capabilities: [] }
    renderPage()

    expect(
      screen.getByTitle('Recording a purchase needs the cost-visibility permission'),
    ).toBeDisabled()
    expect(
      screen.getByTitle('Stock history needs the cost-visibility permission'),
    ).toBeDisabled()
    expect(screen.getByText('Коробка 100×120×50')).toBeInTheDocument()
  })

  it('offers the receipt and history actions to an owner', () => {
    renderPage()

    expect(screen.getByTitle('Record a purchase — adds stock at a price')).toBeEnabled()
    expect(
      screen.getByTitle('Purchases and stock movements').closest('a'),
    ).toHaveAttribute('href', '/inventory/materials/mat-1')
  })
})
