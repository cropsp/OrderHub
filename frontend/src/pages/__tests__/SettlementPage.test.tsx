import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

vi.mock('@/hooks/usePartnerPayouts', () => ({
  usePartnerNames: () => ({ data: { items: [] } }),
  usePreviewSettlement: () => ({
    mutate: previewMutate,
    data: {
      base_amount: '9800.00',
      base_currency: 'UAH',
      computed_amount: '2450.00',
      available_currencies: [],
    },
    isPending: false,
  }),
  useCreateSettlement: () => ({
    mutateAsync: createMutateAsync,
    isPending: false,
  }),
}))

vi.mock('@/hooks/useDebounce', () => ({
  useDebounce: (v: unknown) => v,
}))

function renderPage(
  search = '?start=2026-05-01&end=2026-05-31',
) {
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

describe('SettlementPage', () => {
  beforeEach(() => {
    previewMutate.mockClear()
    createMutateAsync.mockClear()
  })

  it('renders both formula options', () => {
    renderPage()
    expect(
      screen.getByRole('option', { name: /Net Profit \(product-only\)/i }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('option', {
        name: /Items Revenue minus Platform Fees/i,
      }),
    ).toBeInTheDocument()
  })

  it('seeds the period from the start/end query params', () => {
    renderPage()
    expect(screen.getByDisplayValue('2026-05-01')).toBeInTheDocument()
    expect(screen.getByDisplayValue('2026-05-31')).toBeInTheDocument()
  })

  it('falls back to the This Month preset when params are absent or malformed', () => {
    const { unmount } = renderPage('')
    // This Month spans the first to the last day of the current month.
    const now = new Date()
    const first = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
    expect(screen.getByDisplayValue(first)).toBeInTheDocument()
    unmount()

    renderPage('?start=garbage&end=2026-05-31')
    expect(screen.getByDisplayValue(first)).toBeInTheDocument()
    expect(screen.queryByDisplayValue('garbage')).not.toBeInTheDocument()
  })

  it('save button label flips between Save / Close based on checkbox', () => {
    renderPage()
    expect(
      screen.getByRole('button', { name: 'Save Settlement' }),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox'))
    expect(
      screen.queryByRole('button', { name: 'Save Settlement' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Close$/ })).toBeInTheDocument()
  })

  it('preview mutation fires on percent change', async () => {
    renderPage()
    // initial effect fires once with default percent 25
    await waitFor(() => expect(previewMutate).toHaveBeenCalled())
    const initialCalls = previewMutate.mock.calls.length

    const percentInput = screen.getByDisplayValue('25')
    fireEvent.change(percentInput, { target: { value: '40' } })

    await waitFor(() =>
      expect(previewMutate.mock.calls.length).toBeGreaterThan(initialCalls),
    )
    const lastCall = previewMutate.mock.calls[previewMutate.mock.calls.length - 1]
    expect(lastCall[0].percent).toBe('40')
  })

  it('blocks save and shows an error when the partner name is empty', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Save Settlement' }))
    expect(await screen.findByText('Partner name is required')).toBeInTheDocument()
    expect(createMutateAsync).not.toHaveBeenCalled()
  })

  it('saves with the expected payload and navigates back to the finance page', async () => {
    renderPage()
    fireEvent.change(screen.getByPlaceholderText('e.g. Олег'), {
      target: { value: 'Олег' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save Settlement' }))

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1))
    expect(createMutateAsync).toHaveBeenCalledWith({
      partner_name: 'Олег',
      formula_type: 'net_profit_product_only',
      percent: '25',
      period_start: '2026-05-01',
      period_end: '2026-05-31',
      currency: undefined,
      notes: null,
    })
    expect(await screen.findByText('Finance page')).toBeInTheDocument()
  })
})
