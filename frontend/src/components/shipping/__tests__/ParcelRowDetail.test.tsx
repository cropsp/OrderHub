import React from 'react'
import { render, screen, within } from '@testing-library/react'

import type { TrackedParcel, TrackingEvent } from '@/types/westernbid'

import { ParcelRowDetail } from '../ParcelRowDetail'

/**
 * The row expansion (WB-TRACK-2, rule 4) — the only surface for the transition
 * log, which is otherwise dead weight, and the only place WesternBid's own
 * status still appears for a tracked parcel.
 */

const useParcelEventsMock = vi.fn()

vi.mock('@/hooks/useWesternBid', () => ({
  useParcelEvents: (n: string | null, enabled: boolean) =>
    useParcelEventsMock(n, enabled),
}))

function parcel(overrides: Partial<TrackedParcel> = {}): TrackedParcel {
  return {
    tracking_number: '59500007088959',
    carrier: 'NovaPost',
    shipment_id: 'shipment-1',
    order_id: null,
    order_number: null,
    tracking_numbers: [
      { Identifier: 'NovaPost', TrackingNumber: '59500007088959' },
    ],
    state: 'problem',
    status_code: '111',
    status_text: 'Невдала спроба доставки',
    is_overdue: true,
    is_stalled: false,
    days_overdue: 2.34,
    days_since_movement: 1.46,
    recipient_name: 'Jane Doe',
    city_recipient: 'Excelsior',
    recipient_country_code: 'US',
    scheduled_delivery_at: '2026-08-03T12:00:00Z',
    last_movement_at: '2026-08-05T09:00:00Z',
    delivered_at: null,
    no_data_since: null,
    wb_status: 'Sent from Ukraine warehouse',
    payment_status: 'Paid',
    wb_created_at: '2026-07-27T16:41:31Z',
    ...overrides,
  }
}

function event(overrides: Partial<TrackingEvent> = {}): TrackingEvent {
  return {
    status_code: '5',
    status_text: 'Відправлення прямує до  Excelsior.',
    np_tracking_update_date: '2026-08-01T10:05:08Z',
    observed_at: '2026-08-01T18:26:00Z',
    ...overrides,
  }
}

function renderDetail(p: TrackedParcel, events: TrackingEvent[] | undefined, isLoading = false) {
  useParcelEventsMock.mockReturnValue({ data: events, isLoading })
  return render(<ParcelRowDetail parcel={p} />)
}

beforeEach(() => vi.clearAllMocks())

/** The history list specifically — the carrier-numbers block is a list too. */
function historyItems(container: HTMLElement): HTMLElement[] {
  const list = container.querySelector('ol')
  return list ? within(list).getAllByRole('listitem') : []
}

describe('ParcelRowDetail — Nova Poshta history', () => {
  it('shows the transitions in order with their dates', () => {
    const { container } = renderDetail(parcel(), [
      event(),
      event({
        status_code: '111',
        status_text: 'Невдала спроба доставки',
        np_tracking_update_date: '2026-08-04T14:20:00Z',
        observed_at: '2026-08-04T18:26:00Z',
      }),
    ])

    const items = historyItems(container)
    expect(items).toHaveLength(2)
    // Oldest first — "how did it get here" reads forwards.
    expect(within(items[0]).getByText(/прямує до/)).toBeInTheDocument()
    expect(within(items[0]).getByText(/01\.08\.2026/)).toBeInTheDocument()
    expect(within(items[1]).getByText(/Невдала спроба/)).toBeInTheDocument()
    expect(within(items[1]).getByText(/04\.08\.2026/)).toBeInTheDocument()
  })

  it("renders NP's Ukrainian wording verbatim rather than mapping it", () => {
    renderDetail(parcel(), [event()])
    expect(
      screen.getByText(/^Відправлення прямує до\s+Excelsior\.$/),
    ).toBeInTheDocument()
  })

  it('explains a single-event parcel instead of looking broken', () => {
    // Every parcel on prod is in this state today: the log records one row per
    // observed CHANGE, so a parcel polled daily without moving has exactly one.
    const { container } = renderDetail(parcel(), [event()])
    expect(historyItems(container)).toHaveLength(1)
  })

  it('says so plainly when nothing has been recorded yet', () => {
    renderDetail(parcel(), [])
    expect(screen.getByText(/No transitions recorded yet/)).toBeInTheDocument()
  })

  it('does not query history for a parcel with no Nova Poshta number', () => {
    renderDetail(
      parcel({ tracking_number: null, carrier: 'UPS', state: 'untracked' }),
      undefined,
    )

    expect(useParcelEventsMock).toHaveBeenCalledWith(null, true)
    expect(screen.getByText(/check this parcel with UPS directly/i)).toBeInTheDocument()
  })
})

describe('ParcelRowDetail — the no_data case', () => {
  it('names the date it went quiet and admits no status was ever seen', () => {
    // The real prod row: first observed as a stub, so there is no "last
    // resolved status" to fall back on.
    renderDetail(
      parcel({
        state: 'no_data',
        status_code: null,
        status_text: null,
        no_data_since: '2026-08-05T18:26:41Z',
      }),
      [],
    )

    expect(screen.getByText(/stopped returning data on 05\.08\.2026/)).toBeInTheDocument()
    expect(screen.getByText(/No status was ever recorded/)).toBeInTheDocument()
  })

  it('quotes the last status seen when there was one', () => {
    renderDetail(
      parcel({
        state: 'no_data',
        status_text: 'Виїхало з митниці',
        no_data_since: '2026-08-05T18:26:41Z',
      }),
      [],
    )
    expect(screen.getByText(/Last status seen: Виїхало з митниці/)).toBeInTheDocument()
  })
})

describe('ParcelRowDetail — the WesternBid leg', () => {
  it('keeps WB status and payment, labelled as WB’s own leg', () => {
    renderDetail(parcel(), [event()])

    expect(screen.getByText('WesternBid leg')).toBeInTheDocument()
    expect(screen.getByText('Sent from Ukraine warehouse')).toBeInTheDocument()
    expect(screen.getByText('Paid')).toBeInTheDocument()
    expect(
      screen.getByText(/does not know whether the parcel was delivered/),
    ).toBeInTheDocument()
  })
})
