import React from 'react'
import { render, screen } from '@testing-library/react'

import ProgressPanel from '../ProgressPanel'
import type { DraftEvent } from '@/types/draftJob'

function ev(type: string, payload: Record<string, unknown> = {}): DraftEvent {
  return { type, payload, timestamp: '2026-05-19T00:00:00Z', job_state: 'running' }
}

describe('ProgressPanel', () => {
  it('renders all stages, marks completed ones as seen', () => {
    const events: DraftEvent[] = [
      ev('detect.classical.completed', { candidates: 3, k_face: 1 }),
      ev('rectify.completed'),
      ev('face.completed', { found: true }),
    ]
    const { container } = render(<ProgressPanel events={events} state="running" />)
    const stages = container.querySelectorAll('[data-stage]')
    expect(stages.length).toBe(7)

    expect(
      container.querySelector(
        '[data-stage="detect.classical.completed"][data-seen="true"]',
      ),
    ).toBeInTheDocument()
    expect(
      container.querySelector(
        '[data-stage="rectify.completed"][data-seen="true"]',
      ),
    ).toBeInTheDocument()
    expect(
      container.querySelector(
        '[data-stage="export.completed"][data-seen="false"]',
      ),
    ).toBeInTheDocument()
  })

  it('renders the error message when state is failed', () => {
    const events: DraftEvent[] = [
      ev('detect.classical.completed'),
      ev('error', { stage: 'pipeline', message: 'Exceeded 60s' }),
    ]
    render(<ProgressPanel events={events} state="failed" />)
    expect(screen.getByText('Exceeded 60s')).toBeInTheDocument()
  })
})
