import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import ProductDetailPage from '../ProductDetailPage'

/**
 * WH-5 — the product's default packaging box.
 *
 * The retro-consumption backfill reads this field, so a select that looks right
 * but never reaches the PATCH payload would starve it silently. These tests pin
 * the three things that could go wrong that way: the picker offers ACTIVE boxes
 * only, the chosen box lands in the payload, and clearing sends an explicit null
 * rather than an empty string.
 */

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
  stock_quantity: '10.00',
  low_stock_threshold: '5.00',
  material_is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})

const product = (overrides: Record<string, unknown> = {}) => ({
  id: 'prod-1',
  shop_id: 'shop-1',
  title: 'Гаманець «Київ»',
  description: null,
  external_ref: null,
  is_active: true,
  default_packaging_box_id: null,
  image_url: null,
  variants: [],
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
})

const usePackagingMock = vi.fn(() => ({ data: [box()], isLoading: false }))
const useProductMock = vi.fn(() => ({
  data: product(),
  isLoading: false,
  isError: false,
}))
const updateMutateAsync = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  )
  return { ...actual, useParams: () => ({ id: 'prod-1' }) }
})

vi.mock('@/hooks/usePackaging', () => ({
  usePackaging: (includeArchived?: boolean) => usePackagingMock(includeArchived as never),
}))

vi.mock('@/hooks/useProducts', () => ({
  useProduct: () => useProductMock(),
  useUpdateProduct: () => ({ mutateAsync: updateMutateAsync, mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/hooks/useShops', () => ({
  useShops: () => ({ data: [{ id: 'shop-1', name: 'Lamamarka', platform: 'etsy' }] }),
}))

// The BOM editor and the image widget each pull their own data; neither is under
// test here, and stubbing them keeps the module graph flat.
vi.mock('@/components/inventory/BomEditor', () => ({ default: () => <div /> }))
vi.mock('@/components/inventory/ProductImageWidget', () => ({ default: () => <div /> }))

function renderPage() {
  return render(
    <MemoryRouter>
      <ProductDetailPage />
    </MemoryRouter>,
  )
}

function packagingSelect() {
  return screen.getByLabelText(/default packaging/i) as HTMLSelectElement
}

describe('ProductDetailPage — default packaging', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    usePackagingMock.mockReturnValue({ data: [box()], isLoading: false })
    useProductMock.mockReturnValue({ data: product(), isLoading: false, isError: false })
    updateMutateAsync.mockResolvedValue(product({ default_packaging_box_id: 'box-1' }))
  })

  it('offers active boxes only', () => {
    renderPage()

    // includeArchived defaults to false — the server filters on Material.is_active,
    // and the API refuses an archived box here anyway.
    expect(usePackagingMock).toHaveBeenLastCalledWith(undefined)
    expect(
      screen.getByRole('option', { name: /Коробка 100×120×50 \(100×120×50 mm\)/ }),
    ).toBeInTheDocument()
  })

  it('shows the product’s stored box as the current value', () => {
    useProductMock.mockReturnValue({
      data: product({ default_packaging_box_id: 'box-1' }),
      isLoading: false,
      isError: false,
    })

    renderPage()

    expect(packagingSelect().value).toBe('box-1')
  })

  it('sends the chosen box on save', async () => {
    renderPage()

    fireEvent.change(packagingSelect(), { target: { value: 'box-1' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled())
    expect(updateMutateAsync.mock.calls[0][0].data).toMatchObject({
      default_packaging_box_id: 'box-1',
    })
  })

  it('clears with an explicit null, not an empty string', async () => {
    useProductMock.mockReturnValue({
      data: product({ default_packaging_box_id: 'box-1' }),
      isLoading: false,
      isError: false,
    })
    renderPage()

    fireEvent.change(packagingSelect(), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled())
    // '' would be a 422 from the UUID field; null is what clears the column.
    expect(updateMutateAsync.mock.calls[0][0].data.default_packaging_box_id).toBeNull()
  })

  it('keeps a box archived after it was chosen visible instead of reading “none”', () => {
    useProductMock.mockReturnValue({
      data: product({ default_packaging_box_id: 'gone-1' }),
      isLoading: false,
      isError: false,
    })

    renderPage()

    expect(packagingSelect().value).toBe('gone-1')
    expect(screen.getByRole('option', { name: /archived box/i })).toBeDisabled()
  })
})
