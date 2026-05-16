import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import CalculateSettlementModal from '../CalculateSettlementModal'

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

describe('CalculateSettlementModal', () => {
  beforeEach(() => {
    previewMutate.mockClear()
    createMutateAsync.mockClear()
  })

  it('renders both formula options', () => {
    render(
      <CalculateSettlementModal
        isOpen={true}
        onClose={() => {}}
        shopId="shop-1"
        defaultPeriodStart="2026-05-01"
        defaultPeriodEnd="2026-05-31"
      />,
    )
    expect(
      screen.getByRole('option', { name: /Net Profit \(product-only\)/i }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('option', {
        name: /Items Revenue minus Platform Fees/i,
      }),
    ).toBeInTheDocument()
  })

  it('save button label flips between Save / Close based on checkbox', () => {
    render(
      <CalculateSettlementModal
        isOpen={true}
        onClose={() => {}}
        shopId="shop-1"
        defaultPeriodStart="2026-05-01"
        defaultPeriodEnd="2026-05-31"
      />,
    )
    expect(
      screen.getByRole('button', { name: 'Save Settlement' }),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox'))
    // After unchecking, the save button label becomes "Close".
    expect(
      screen.queryByRole('button', { name: 'Save Settlement' }),
    ).not.toBeInTheDocument()
    // Two "Close"-named buttons may exist (dialog X icon + footer button).
    const closeButtons = screen.getAllByRole('button', { name: /^Close$/ })
    expect(closeButtons.length).toBeGreaterThan(0)
  })

  it('preview mutation fires on percent change', async () => {
    render(
      <CalculateSettlementModal
        isOpen={true}
        onClose={() => {}}
        shopId="shop-1"
        defaultPeriodStart="2026-05-01"
        defaultPeriodEnd="2026-05-31"
      />,
    )
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
})
