import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'

import DraftGenerator from '../DraftGenerator'
import type { UseDraftJobResult } from '@/hooks/useDraftJob'

// Mock the hook and toast/attachment APIs so the modal can be exercised
// without any real network / SSE machinery.
vi.mock('@/hooks/useDraftJob', () => ({
  useDraftJob: vi.fn(),
}))
vi.mock('@/api/attachments', () => ({
  attachmentsApi: {
    download: vi.fn(() =>
      Promise.resolve(new Blob([new Uint8Array([1])], { type: 'image/png' })),
    ),
  },
}))
vi.mock('@/components/ui/Toast', () => ({
  useToastStore: () => ({ addToast: vi.fn() }),
}))

import { useDraftJob } from '@/hooks/useDraftJob'

const baseJob: UseDraftJobResult = {
  state: 'running',
  events: [],
  result: null,
  reviewContext: null,
  error: null,
  jobId: null,
  start: vi.fn(),
  submitCorners: vi.fn(),
  cancel: vi.fn(),
  retry: vi.fn(),
}

beforeAll(() => {
  ;(global as unknown as { URL: typeof URL }).URL.createObjectURL = vi.fn(
    () => 'blob:mock',
  )
  ;(global as unknown as { URL: typeof URL }).URL.revokeObjectURL = vi.fn()
})

describe('DraftGenerator', () => {
  it('renders ProgressPanel and dialog title when running', () => {
    ;(useDraftJob as unknown as ReturnType<typeof vi.fn>).mockReturnValue(baseJob)
    render(
      <DraftGenerator
        isOpen={true}
        onClose={() => {}}
        orderId="o1"
        photoAttachmentId="p1"
        photoFilename="test.jpg"
      />,
    )
    expect(screen.getByText(/Generate Draft from test.jpg/)).toBeInTheDocument()
    expect(screen.getByText('Running pipeline...')).toBeInTheDocument()
  })

  it('shows Download Draft button when state=ready', () => {
    ;(useDraftJob as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      ...baseJob,
      state: 'ready',
      result: { resultAttachmentId: 'r1' },
      jobId: 'j1',
    })
    render(
      <DraftGenerator
        isOpen={true}
        onClose={() => {}}
        orderId="o1"
        photoAttachmentId="p1"
        photoFilename="test.jpg"
      />,
    )
    expect(
      screen.getByRole('button', { name: /Download Draft/ }),
    ).toBeInTheDocument()
  })

  it('shows Retry button when state=failed', async () => {
    ;(useDraftJob as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      ...baseJob,
      state: 'failed',
      error: 'Exceeded 60s',
    })
    render(
      <DraftGenerator
        isOpen={true}
        onClose={() => {}}
        orderId="o1"
        photoAttachmentId="p1"
        photoFilename="test.jpg"
      />,
    )
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Retry/ })).toBeInTheDocument(),
    )
  })

  it('calls start() only once under React.StrictMode double-invoke', () => {
    const startSpy = vi.fn()
    ;(useDraftJob as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
      ...baseJob,
      state: 'idle',
      start: startSpy,
    })
    render(
      <React.StrictMode>
        <DraftGenerator
          isOpen={true}
          onClose={() => {}}
          orderId="o1"
          photoAttachmentId="p1"
          photoFilename="test.jpg"
        />
      </React.StrictMode>,
    )
    expect(startSpy).toHaveBeenCalledTimes(1)
    expect(startSpy).toHaveBeenCalledWith('p1')
  })
})
