import React from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import type { TrackedParcel, TrackingCounts } from '@/types/westernbid'

import WesternBidPage from '../WesternBidPage'

/**
 * WB-TRACK-2 — the parcel monitoring page.
 *
 * These assert the behaviours the sprint exists for: the exception-first
 * grouping, that untracked parcels are never silently dropped, that the three
 * attention reasons stay distinguishable, and that the delivered group costs
 * nothing until someone opens it. `STATEMENT-UI-TESTS` is the standing lesson —
 * a component shipped onto an untested page and filed as debt the same day.
 */

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

const useTrackingOverviewMock = vi.fn()
const useDeliveredParcelsMock = vi.fn()
const refreshMutate = vi.fn()

vi.mock('@/hooks/useWesternBid', () => ({
  useTrackingOverview: () => useTrackingOverviewMock(),
  useDeliveredParcels: (limit: number, offset: number, enabled: boolean) =>
    useDeliveredParcelsMock(limit, offset, enabled),
  useRefreshTracking: () => ({ mutate: refreshMutate, isPending: false }),
  useParcelEvents: () => ({ data: [], isLoading: false }),
}))

function parcel(overrides: Partial<TrackedParcel> = {}): TrackedParcel {
  return {
    tracking_number: '59500007147707',
    carrier: 'NovaPost',
    shipment_id: crypto.randomUUID(),
    order_id: null,
    order_number: null,
    tracking_numbers: [
      { Identifier: 'NovaPost', TrackingNumber: '59500007147707' },
    ],
    state: 'moving',
    status_code: '5',
    status_text: 'Відправлення прямує до  Phoenix.',
    is_overdue: false,
    is_stalled: false,
    days_overdue: null,
    days_since_movement: 0.4,
    recipient_name: 'Jane Doe',
    city_recipient: 'Phoenix',
    recipient_country_code: 'US',
    scheduled_delivery_at: null,
    last_movement_at: new Date().toISOString(),
    delivered_at: null,
    no_data_since: null,
    wb_status: 'Parcel created',
    payment_status: 'Paid',
    wb_created_at: new Date().toISOString(),
    ...overrides,
  }
}

// The three attention reasons, drawn from the real prod records so the test
// fails if any of them stops being distinguishable from the others.
const OVERDUE = parcel({
  tracking_number: '59500007044916',
  city_recipient: 'Belews Creek',
  is_overdue: true,
  days_overdue: 12.64,
  days_since_movement: 1.06,
  status_text: 'Відправлення у  Belews Creek. Очікуйте повідомлення про прибуття',
})

const PROBLEM = parcel({
  tracking_number: '59500007088959',
  state: 'problem',
  status_code: '111',
  status_text:
    "Невдала спроба доставки через відсутність Одержувача на адресі або зв'язку з ним.",
  is_overdue: true,
  days_overdue: 2.34,
  days_since_movement: 1.46,
})

const NO_DATA = parcel({
  tracking_number: '59500007112662',
  state: 'no_data',
  status_code: null,
  status_text: null,
  city_recipient: null,
  days_since_movement: null,
  no_data_since: '2026-08-05T18:26:41Z',
})

const UNTRACKED_UPS = parcel({
  tracking_number: null,
  carrier: 'UPS',
  state: 'untracked',
  status_code: null,
  status_text: null,
  city_recipient: null,
  days_since_movement: null,
  recipient_name: 'Domenik Karer',
  recipient_country_code: 'CH',
  tracking_numbers: [
    { Identifier: 'WesternBid', TrackingNumber: 'WBX000000241486' },
    { Identifier: 'UPS', TrackingNumber: '1Z08W335D906259863' },
  ],
})

const CANCELED = parcel({
  tracking_number: null,
  carrier: 'NovaPost',
  state: 'untracked',
  status_code: null,
  status_text: null,
  city_recipient: null,
  days_since_movement: null,
  recipient_name: 'Dusty Cain',
  wb_status: 'Parcel canceled',
  tracking_numbers: [
    { Identifier: 'WesternBid', TrackingNumber: 'WBX100000000001' },
  ],
})

function counts(overrides: Partial<TrackingCounts> = {}): TrackingCounts {
  return {
    total: 6,
    delivered: 21,
    moving: 3,
    problem: 1,
    no_data: 1,
    untracked: 2,
    overdue: 2,
    stalled: 0,
    ...overrides,
  }
}

function renderPage(parcels: TrackedParcel[], countOverrides = {}) {
  useTrackingOverviewMock.mockReturnValue({
    data: {
      counts: counts(countOverrides),
      parcels,
      polled_at: '2026-08-05T18:26:52Z',
      stalled_days: 3,
    },
    isLoading: false,
  })
  return render(
    <MemoryRouter>
      <WesternBidPage />
    </MemoryRouter>,
  )
}

function group(name: RegExp) {
  return screen.getByRole('button', { name }).closest('section') as HTMLElement
}

beforeEach(() => {
  vi.clearAllMocks()
  useDeliveredParcelsMock.mockReturnValue({ data: undefined, isLoading: false })
})

describe('WesternBidPage — grouping', () => {
  it('puts every flagged parcel in the attention group and nothing else', () => {
    renderPage([OVERDUE, PROBLEM, NO_DATA, parcel(), UNTRACKED_UPS])

    const attention = group(/Needs attention/)
    expect(within(attention).getByText('59500007044916')).toBeInTheDocument()
    expect(within(attention).getByText('59500007088959')).toBeInTheDocument()
    expect(within(attention).getByText('59500007112662')).toBeInTheDocument()
    // The clean moving parcel is NOT in attention — the whole point of the page.
    expect(within(attention).queryByText('59500007147707')).not.toBeInTheDocument()
  })

  it('leads with the worst parcel, and puts action-needed states above merely-late ones', () => {
    renderPage([OVERDUE, PROBLEM, NO_DATA])

    const numbers = within(group(/Needs attention/))
      .getAllByText(/^5950000\d+$/)
      .map((el) => el.textContent)

    // problem, then no_data, then overdue by days_overdue descending.
    expect(numbers).toEqual([
      '59500007088959',
      '59500007112662',
      '59500007044916',
    ])
  })

  it('shows the delivered count from the full-set counts, not from fetched rows', () => {
    renderPage([parcel()])

    // Zero delivered rows were fetched — the header must still say 21.
    const delivered = group(/Delivered/)
    expect(within(delivered).getByText('21')).toBeInTheDocument()
  })

  it('reports a stale poll so day-old data is never read as current', () => {
    renderPage([parcel()])
    expect(screen.getByText(/Last polled 05\.08\.2026/)).toBeInTheDocument()
  })
})

describe('WesternBidPage — untracked parcels', () => {
  it('names them, labels the carrier and shows a number to check by hand', () => {
    renderPage([UNTRACKED_UPS, parcel()])

    const untracked = group(/Untracked/)
    expect(within(untracked).getByText('Domenik Karer')).toBeInTheDocument()
    expect(within(untracked).getAllByText('UPS').length).toBeGreaterThan(0)
    // Without this the operator is told "check by hand" and given nothing.
    expect(within(untracked).getByText(/1Z08W335D906259863/)).toBeInTheDocument()
  })

  it("keeps WesternBid's own status inline, which is all a canceled parcel has", () => {
    renderPage([CANCELED])

    const untracked = group(/Untracked/)
    expect(within(untracked).getByText('Dusty Cain')).toBeInTheDocument()
    expect(within(untracked).getByText(/Parcel canceled/)).toBeInTheDocument()
  })
})

describe('WesternBidPage — attention reasons', () => {
  it('distinguishes problem, no_data and overdue from each other', () => {
    renderPage([OVERDUE, PROBLEM, NO_DATA])

    const attention = group(/Needs attention/)
    expect(within(attention).getByText('Problem')).toBeInTheDocument()
    expect(within(attention).getByText('No NP data')).toBeInTheDocument()
    expect(within(attention).getByText('12.6d overdue')).toBeInTheDocument()
    // …and the same parcel can carry two reasons at once.
    expect(within(attention).getByText('2.3d overdue')).toBeInTheDocument()
  })

  it('renders a reassuring state when nothing needs attention', () => {
    renderPage([parcel()], { problem: 0, no_data: 0, overdue: 0, stalled: 0 })

    expect(
      screen.getByText(/Nothing needs attention/),
    ).toBeInTheDocument()
  })
})

// Both cases use a flagged parcel because only the attention group is open by
// default — which is itself the layout working: a clean in-transit parcel is
// not on screen until someone asks for it.
describe('WesternBidPage — the order link', () => {
  it('links a matched parcel to its order', () => {
    renderPage([{ ...OVERDUE, order_id: 'order-1', order_number: '1042' }])

    const link = screen.getByRole('link', { name: '1042' })
    expect(link).toHaveAttribute('href', '/orders/order-1')
  })

  it('says "not linked" rather than implying the order is missing', () => {
    // 83 of 84 prod parcels look like this — `wb_parcel.order_id` is populated
    // only when a label was fetched through OrderHub.
    renderPage([OVERDUE])
    expect(screen.getByText('Not linked')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /^\d+$/ })).not.toBeInTheDocument()
  })
})

describe('WesternBidPage — the delivered group', () => {
  it('fetches nothing until it is opened', () => {
    renderPage([parcel()])

    expect(useDeliveredParcelsMock).toHaveBeenCalledWith(25, 0, false)
    expect(useDeliveredParcelsMock).not.toHaveBeenCalledWith(25, 0, true)

    fireEvent.click(screen.getByRole('button', { name: /Delivered/ }))

    expect(useDeliveredParcelsMock).toHaveBeenCalledWith(25, 0, true)
  })
})
