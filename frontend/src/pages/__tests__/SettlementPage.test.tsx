import React from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import SettlementPage from '../SettlementPage'

// ShellPage pulls in the full auth + shops stack; stub it down to a passthrough.
vi.mock('../ShellPage', () => ({
  default: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div>
      <h1>{title}</h1>
      {children}
    </div>
  ),
}))

const previewMutate = vi.fn()
const createMutateAsync = vi.fn().mockResolvedValue({})

const PARTNER_ID = 'partner-1'

// PARTNER-CONFIG-1: the page reads the partner's configuration on this shop and
// adopts its percent / basis / currency as the defaults.
let configItems: unknown[] = [
  {
    id: 'cfg-1',
    shop_id: 'shop-1',
    partner_id: PARTNER_ID,
    partner_name: 'Ксенія',
    percent: '30.00',
    basis: 'turnover',
    settlement_currency: 'USD',
    is_active: true,
    last_period_end: null,
  },
]

let previewData: Record<string, unknown> = {
  base_amount: '9800.00',
  base_currency: 'USD',
  computed_amount: '2940.00',
  available_currencies: [],
  fx_rate_used: null,
  terms: [],
  quality: null,
  overlapping: [],
  last_period_end: null,
}

// vi.mock replaces the module WHOLESALE — every hook the page calls must appear
// here or it throws at render.
vi.mock('@/hooks/usePartnerPayouts', () => ({
  usePreviewSettlement: () => ({
    mutate: previewMutate,
    data: previewData,
    isPending: false,
  }),
  useCreateSettlement: () => ({
    mutateAsync: createMutateAsync,
    isPending: false,
  }),
}))

vi.mock('@/hooks/usePartners', () => ({
  useShopPartnerConfigs: () => ({
    data: { items: configItems },
    isLoading: false,
  }),
}))

vi.mock('@/hooks/useDebounce', () => ({
  useDebounce: (v: unknown) => v,
}))

function renderPage(search = '?start=2026-05-01&end=2026-05-31') {
  return render(
    <MemoryRouter initialEntries={[`/shops/shop-1/finance/settlement${search}`]}>
      <Routes>
        <Route
          path="/shops/:shopId/finance/settlement"
          element={<SettlementPage />}
        />
        <Route path="/shops/:shopId/finance" element={<div>Finance page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

function selectPartner() {
  fireEvent.change(screen.getByLabelText('Partner'), {
    target: { value: PARTNER_ID },
  })
}

describe('SettlementPage', () => {
  beforeEach(() => {
    previewMutate.mockClear()
    createMutateAsync.mockClear()
    configItems = [
      {
        id: 'cfg-1',
        shop_id: 'shop-1',
        partner_id: PARTNER_ID,
        partner_name: 'Ксенія',
        percent: '30.00',
        basis: 'turnover',
        settlement_currency: 'USD',
        is_active: true,
        last_period_end: null,
      },
    ]
    previewData = {
      base_amount: '9800.00',
      base_currency: 'USD',
      computed_amount: '2940.00',
      available_currencies: [],
      fx_rate_used: null,
      terms: [],
      quality: null,
      overlapping: [],
      last_period_end: null,
    }
  })

  it('offers only the two selectable bases — legacy formulas are read-only', () => {
    renderPage()
    // Scoped to the Basis select: the partner options also spell out "% of
    // turnover", which is the point of showing the config inline.
    const basis = within(screen.getByLabelText('Basis'))
    expect(basis.getByRole('option', { name: /% of Turnover/i })).toBeInTheDocument()
    expect(basis.getByRole('option', { name: /% of Profit/i })).toBeInTheDocument()
    expect(basis.queryAllByRole('option')).toHaveLength(2)
    expect(screen.queryByRole('option', { name: /legacy/i })).not.toBeInTheDocument()
    expect(
      screen.queryByRole('option', { name: /Items Revenue minus Platform Fees/i }),
    ).not.toBeInTheDocument()
  })

  it('adopts the partner’s configured percent, basis and currency on selection', () => {
    renderPage()
    selectPartner()
    expect(screen.getByLabelText('Percent')).toHaveValue(30)
    expect(screen.getByLabelText('Basis')).toHaveValue('turnover')
    // Settlement currency is configuration, not a dropdown choice.
    expect(screen.getByText('USD')).toBeInTheDocument()
  })

  it('defaults the next period to the day after the last settled one', () => {
    configItems = [{ ...(configItems[0] as object), last_period_end: '2026-05-31' }]
    renderPage()
    selectPartner()
    expect(screen.getByLabelText('Period start')).toHaveValue('2026-06-01')
  })

  it('flags an override and can reset back to the configured defaults', () => {
    renderPage()
    selectPartner()
    fireEvent.change(screen.getByLabelText('Percent'), { target: { value: '45' } })
    expect(screen.getByText(/Overriding the configured 30%/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Reset to configured/i }))
    expect(screen.getByLabelText('Percent')).toHaveValue(30)
    expect(screen.queryByText(/Overriding the configured/i)).not.toBeInTheDocument()
  })

  it('seeds the period from the start/end query params', () => {
    renderPage()
    expect(screen.getByDisplayValue('2026-05-01')).toBeInTheDocument()
    expect(screen.getByDisplayValue('2026-05-31')).toBeInTheDocument()
  })

  it('falls back to the This Month preset when params are absent or malformed', () => {
    const { unmount } = renderPage('')
    const now = new Date()
    const first = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
    expect(screen.getByDisplayValue(first)).toBeInTheDocument()
    unmount()

    renderPage('?start=garbage&end=2026-05-31')
    expect(screen.getByDisplayValue(first)).toBeInTheDocument()
    expect(screen.queryByDisplayValue('garbage')).not.toBeInTheDocument()
  })

  it('preview fires only once a partner is selected, then on percent change', async () => {
    renderPage()
    // No partner → no preview: the base depends on the partner's config.
    expect(previewMutate).not.toHaveBeenCalled()

    selectPartner()
    await waitFor(() => expect(previewMutate).toHaveBeenCalled())
    const initialCalls = previewMutate.mock.calls.length

    fireEvent.change(screen.getByLabelText('Percent'), { target: { value: '40' } })
    await waitFor(() =>
      expect(previewMutate.mock.calls.length).toBeGreaterThan(initialCalls),
    )
    const lastCall = previewMutate.mock.calls[previewMutate.mock.calls.length - 1]
    expect(lastCall[0].percent).toBe('40')
    expect(lastCall[0].partner_id).toBe(PARTNER_ID)
  })

  it('blocks save until a partner is selected', async () => {
    renderPage()
    expect(screen.getByRole('button', { name: 'Save Settlement' })).toBeDisabled()
    expect(createMutateAsync).not.toHaveBeenCalled()
  })

  it('renders the base-quality warnings without blocking save', () => {
    previewData = {
      ...previewData,
      quality: {
        total_orders: 40,
        orders_missing_cost: 37,
        orders_missing_platform_fee: 12,
        etsy_months_without_statement: [],
        etsy_refunds_unbooked: false,
        fx_blocker: null,
      },
    }
    renderPage()
    selectPartner()
    expect(screen.getByText(/37 of 40 orders/i)).toBeInTheDocument()
    expect(screen.getByText(/12 orders have no platform fee/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save Settlement' })).toBeEnabled()
  })

  it('blocks save when the period overlaps an existing settlement', () => {
    previewData = {
      ...previewData,
      overlapping: [
        { id: 's-1', period_start: '2026-05-01', period_end: '2026-05-31' },
      ],
    }
    renderPage()
    selectPartner()
    expect(screen.getByText(/overlaps an existing settlement/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save Settlement' })).toBeDisabled()
  })

  it('blocks save when FX cannot convert a term in the period', () => {
    previewData = {
      ...previewData,
      base_amount: null,
      computed_amount: null,
      quality: {
        total_orders: 10,
        orders_missing_cost: 0,
        orders_missing_platform_fee: 0,
        etsy_months_without_statement: [],
        etsy_refunds_unbooked: false,
        fx_blocker: 'no usable UAH/USD rate is configured',
      },
    }
    renderPage()
    selectPartner()
    expect(screen.getByText(/no usable UAH\/USD rate/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save Settlement' })).toBeDisabled()
  })

  it('shows the frozen FX rate and the term breakdown when one applied', () => {
    previewData = {
      ...previewData,
      fx_rate_used: '41.500000',
      terms: [
        { name: 'items_revenue', currency: 'USD', amount: '1000.00', converted: '1000.00' },
        { name: 'allocated_overhead', currency: 'UAH', amount: '-4150.00', converted: '-100.00' },
      ],
    }
    renderPage()
    selectPartner()
    expect(screen.getByText(/41.5 UAH\/USD/)).toBeInTheDocument()
    expect(screen.getByText(/allocated overhead \(UAH\)/)).toBeInTheDocument()
    expect(screen.getByText('-100.00 USD')).toBeInTheDocument()
  })

  it('saves with partner_id and the selected basis, then navigates back', async () => {
    renderPage()
    selectPartner()
    fireEvent.click(screen.getByRole('button', { name: 'Save Settlement' }))

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1))
    expect(createMutateAsync).toHaveBeenCalledWith({
      partner_id: PARTNER_ID,
      formula_type: 'turnover',
      // Normalised through Number() before sending, as it always was — the
      // backend quantizes to 2dp anyway.
      percent: '30',
      period_start: '2026-05-01',
      period_end: '2026-05-31',
      notes: null,
    })
    expect(await screen.findByText('Finance page')).toBeInTheDocument()
  })

  it('tells the operator where to configure partners when none exist', () => {
    configItems = []
    renderPage()
    expect(
      screen.getByText(/No partners are configured on this store/i),
    ).toBeInTheDocument()
  })
})
