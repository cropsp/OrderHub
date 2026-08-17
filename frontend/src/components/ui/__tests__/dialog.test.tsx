import React from 'react'
import { render } from '@testing-library/react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../dialog'

/**
 * MAT-UI-2. The primitive used to default to `sm:max-w-sm`, a media-query
 * utility that twMerge cannot reconcile with an unprefixed caller `max-w-*`:
 * both classes survive and the `sm:` one wins on source order above 640px, so
 * every dialog that asked for a width silently rendered as a 384px column.
 * These tests read the merged class list, which is the whole mechanism — jsdom
 * has no layout engine and vitest does not load the Tailwind plugin, so the
 * geometric half is verified in a real browser.
 */
function renderContent(className?: string) {
  render(
    <Dialog open>
      <DialogContent className={className}>
        <DialogHeader>
          <DialogTitle>Title</DialogTitle>
          <DialogDescription>Description</DialogDescription>
        </DialogHeader>
      </DialogContent>
    </Dialog>,
  )
  return document.querySelector('[data-slot=dialog-content]') as HTMLElement
}

describe('DialogContent width', () => {
  it("lets a caller's unprefixed max-w win outright", () => {
    const content = renderContent('max-w-2xl')

    expect(content.classList.contains('max-w-2xl')).toBe(true)
    // The default must be *removed* by twMerge, not merely outranked.
    expect(content.classList.contains('max-w-sm')).toBe(false)
    expect(content.classList.contains('sm:max-w-sm')).toBe(false)
  })

  it('keeps the viewport gutter alongside the caller width', () => {
    const content = renderContent('max-w-2xl')

    // The gutter lives in the `w-` group precisely so it is not collateral
    // damage when a caller replaces the `max-w-` group.
    expect(content.classList.contains('w-[calc(100%-2rem)]')).toBe(true)
  })

  it('falls back to its own width cap when the caller asks for none', () => {
    const content = renderContent()

    expect(content.classList.contains('max-w-sm')).toBe(true)
  })
})

describe('DialogContent height', () => {
  it('caps height against the viewport by default', () => {
    const content = renderContent()

    expect(content.classList.contains('max-h-[calc(100dvh-2rem)]')).toBe(true)
  })

  it('lets a caller override the cap', () => {
    const content = renderContent('max-h-[94vh]')

    expect(content.classList.contains('max-h-[94vh]')).toBe(true)
    expect(content.classList.contains('max-h-[calc(100dvh-2rem)]')).toBe(false)
  })

  it('scrolls itself when the caller builds no scroller of its own', () => {
    const content = renderContent()

    expect(content.classList.contains('overflow-y-auto')).toBe(true)
    // A lone `overflow-y-auto` promotes the x axis from visible to auto, which
    // hands a horizontal scrollbar to every footer that hangs past the content
    // box on negative margins.
    expect(content.classList.contains('overflow-x-hidden')).toBe(true)
  })

  it('yields the scroll to a caller that clips its own corners', () => {
    const content = renderContent('overflow-hidden')

    expect(content.classList.contains('overflow-hidden')).toBe(true)
    expect(content.classList.contains('overflow-y-auto')).toBe(false)
    expect(content.classList.contains('overflow-x-hidden')).toBe(false)
  })
})
