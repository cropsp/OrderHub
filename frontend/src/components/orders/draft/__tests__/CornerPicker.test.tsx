import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'

import CornerPicker from '../CornerPicker'

function mockBlob(): Blob {
  return new Blob([new Uint8Array([1, 2, 3])], { type: 'image/png' })
}

beforeAll(() => {
  // URL.createObjectURL is unavailable in jsdom.
  ;(global as unknown as { URL: typeof URL }).URL.createObjectURL = vi.fn(
    () => 'blob:mock',
  )
  ;(global as unknown as { URL: typeof URL }).URL.revokeObjectURL = vi.fn()
  // Element.setPointerCapture / releasePointerCapture are no-ops in jsdom.
  Element.prototype.setPointerCapture = vi.fn() as unknown as typeof Element.prototype.setPointerCapture
  Element.prototype.releasePointerCapture = vi.fn() as unknown as typeof Element.prototype.releasePointerCapture
})

describe('CornerPicker', () => {
  it('renders 4 corner markers after image load with initial corners', () => {
    const initialCorners = [
      [10, 10],
      [100, 10],
      [100, 100],
      [10, 100],
    ]
    const { container } = render(
      <CornerPicker
        imageBlob={mockBlob()}
        initialCorners={initialCorners}
        onSubmit={() => {}}
        onCancel={() => {}}
      />,
    )
    const img = container.querySelector('img')!
    // Stub natural size + container bbox so onImageLoad seeds markers.
    Object.defineProperty(img, 'naturalWidth', { value: 1000, configurable: true })
    Object.defineProperty(img, 'naturalHeight', { value: 1000, configurable: true })
    const containerEl = container.querySelector(
      '[data-testid="corner-picker-container"]',
    )! as HTMLDivElement
    containerEl.getBoundingClientRect = () => ({
      x: 0, y: 0, width: 200, height: 200,
      left: 0, right: 200, top: 0, bottom: 200, toJSON: () => ({}),
    } as DOMRect)
    fireEvent.load(img)

    const markers = container.querySelectorAll('[data-corner]')
    expect(markers.length).toBe(4)
  })

  it('calls onSubmit with 4 corners in original-image px on Submit click', () => {
    const initialCorners = [
      [100, 100],
      [900, 100],
      [900, 900],
      [100, 900],
    ]
    const onSubmit = vi.fn()
    const { container } = render(
      <CornerPicker
        imageBlob={mockBlob()}
        initialCorners={initialCorners}
        onSubmit={onSubmit}
        onCancel={() => {}}
      />,
    )
    const img = container.querySelector('img')!
    Object.defineProperty(img, 'naturalWidth', { value: 1000, configurable: true })
    Object.defineProperty(img, 'naturalHeight', { value: 1000, configurable: true })
    const containerEl = container.querySelector(
      '[data-testid="corner-picker-container"]',
    )! as HTMLDivElement
    containerEl.getBoundingClientRect = () => ({
      x: 0, y: 0, width: 100, height: 100,
      left: 0, right: 100, top: 0, bottom: 100, toJSON: () => ({}),
    } as DOMRect)
    fireEvent.load(img)

    fireEvent.click(screen.getByRole('button', { name: 'Submit corners' }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    const submitted = onSubmit.mock.calls[0][0] as number[][]
    expect(submitted.length).toBe(4)
    // 100/1000 × 1000 (because we scale down then back up) → 100
    expect(submitted[0][0]).toBeCloseTo(100, 5)
    expect(submitted[1][0]).toBeCloseTo(900, 5)
  })

  it('calls onCancel when Cancel is clicked', () => {
    const onCancel = vi.fn()
    render(
      <CornerPicker
        imageBlob={mockBlob()}
        initialCorners={[[0, 0], [1, 0], [1, 1], [0, 1]]}
        onSubmit={() => {}}
        onCancel={onCancel}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
