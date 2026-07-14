import React from 'react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import ProductImageWidget from '../ProductImageWidget'
import type { Product } from '@/types/inventory'

const uploadMutate = vi.fn()
const deleteMutate = vi.fn()
const pullMutate = vi.fn()
let imageBlob: Blob | undefined

vi.mock('@/hooks/useProducts', () => ({
  useProductImage: () => ({ data: imageBlob, isLoading: false }),
  useUploadProductImage: () => ({ mutate: uploadMutate, isPending: false }),
  useDeleteProductImage: () => ({ mutate: deleteMutate, isPending: false }),
  usePullProductImageFromShopify: () => ({ mutate: pullMutate, isPending: false }),
}))

vi.mock('@/components/ui/Toast', () => ({
  useToastStore: () => vi.fn(),
}))

// jsdom implements neither of these.
beforeAll(() => {
  ;(global as unknown as { URL: typeof URL }).URL.createObjectURL = vi.fn(() => 'blob:mock')
  ;(global as unknown as { URL: typeof URL }).URL.revokeObjectURL = vi.fn()
})

const product = (image_url: string | null): Product => ({
  id: 'p1',
  shop_id: 's1',
  title: 'Leather Wallet',
  description: null,
  is_active: true,
  variants: [],
  image_url,
})

describe('ProductImageWidget', () => {
  it('shows a placeholder and an Upload button when the product has no image', () => {
    imageBlob = undefined
    render(<ProductImageWidget product={product(null)} isShopify={false} />)

    expect(screen.getByTestId('product-image-placeholder')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /upload/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('renders the image with Replace + Remove when the product has one', () => {
    imageBlob = new Blob([new Uint8Array([1])], { type: 'image/png' })
    render(<ProductImageWidget product={product('/api/products/p1/image')} isShopify={false} />)

    expect(screen.getByRole('img', { name: 'Leather Wallet' })).toHaveAttribute('src', 'blob:mock')
    expect(screen.getByRole('button', { name: /replace/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /remove/i })).toBeInTheDocument()
    expect(screen.queryByTestId('product-image-placeholder')).not.toBeInTheDocument()
  })

  it('shows Pull from Shopify only for Shopify-sourced products', () => {
    imageBlob = undefined
    const { unmount } = render(<ProductImageWidget product={product(null)} isShopify />)
    expect(screen.getByRole('button', { name: /pull from shopify/i })).toBeInTheDocument()
    unmount()

    render(<ProductImageWidget product={product(null)} isShopify={false} />)
    expect(screen.queryByRole('button', { name: /pull from shopify/i })).not.toBeInTheDocument()
  })

  it('rejects an oversized file client-side without calling the upload mutation', () => {
    imageBlob = undefined
    render(<ProductImageWidget product={product(null)} isShopify={false} />)

    const input = screen.getByTestId('product-image-input') as HTMLInputElement
    const big = new File(['x'], 'big.png', { type: 'image/png' })
    Object.defineProperty(big, 'size', { value: 6 * 1024 * 1024 })
    Object.defineProperty(input, 'files', { value: [big] })
    input.dispatchEvent(new Event('change', { bubbles: true }))

    expect(uploadMutate).not.toHaveBeenCalled()
  })
})
