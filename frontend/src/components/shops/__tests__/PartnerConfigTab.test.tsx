import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { PartnerConfigTab } from '../PartnerConfigTab'

const createPartner = vi.fn()
const upsertMutate = vi.fn()
const upsertMutateAsync = vi.fn().mockResolvedValue({})
const removeMutate = vi.fn()

let configItems: unknown[] = []
let partnerItems: unknown[] = []

// vi.mock replaces the module wholesale — every hook the component calls must
// be listed here or it throws at render.
vi.mock('@/hooks/usePartners', () => ({
  useShopPartnerConfigs: () => ({ data: { items: configItems }, isLoading: false }),
  usePartners: () => ({ data: { items: partnerItems } }),
  useCreatePartner: () => ({ mutateAsync: createPartner }),
  useUpsertShopPartnerConfig: () => ({
    mutate: upsertMutate,
    mutateAsync: upsertMutateAsync,
  }),
  useDeleteShopPartnerConfig: () => ({ mutate: removeMutate }),
}))

const CONFIG = {
  id: 'cfg-1',
  shop_id: 'shop-1',
  partner_id: 'partner-1',
  partner_name: 'Ксенія',
  percent: '30.00',
  basis: 'turnover',
  settlement_currency: 'USD',
  is_active: true,
  last_period_end: '2026-05-31',
}

describe('PartnerConfigTab', () => {
  beforeEach(() => {
    createPartner.mockReset().mockResolvedValue({ id: 'partner-new' })
    upsertMutate.mockReset()
    upsertMutateAsync.mockReset().mockResolvedValue({})
    removeMutate.mockReset()
    configItems = []
    partnerItems = []
  })

  it('tells the operator to save the store before configuring partners', () => {
    render(<PartnerConfigTab shopId={null} />)
    expect(screen.getByText(/Save the store first/i)).toBeInTheDocument()
  })

  it('lists the shop’s configured partners with their defaults', () => {
    configItems = [CONFIG]
    render(<PartnerConfigTab shopId="shop-1" />)
    expect(screen.getByText('Ксенія')).toBeInTheDocument()
    expect(screen.getByLabelText('Percent for Ксенія')).toHaveValue(30)
    // Scoped to the row: "USD" also appears in the add-partner currency picker.
    const row = screen.getByText('Ксенія').closest('tr') as HTMLElement
    expect(row).toHaveTextContent('USD')
    expect(row).toHaveTextContent('2026-05-31')
  })

  it('creates the partner identity then attaches it to the shop', async () => {
    render(<PartnerConfigTab shopId="shop-1" />)
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Олег' } })
    fireEvent.click(screen.getByRole('button', { name: /Add/i }))

    await waitFor(() => expect(createPartner).toHaveBeenCalledWith({ name: 'Олег' }))
    await waitFor(() =>
      expect(upsertMutateAsync).toHaveBeenCalledWith({
        partnerId: 'partner-new',
        payload: {
          percent: '25',
          basis: 'profit',
          settlement_currency: 'USD',
          is_active: true,
        },
      }),
    )
  })

  it('reuses an existing partner instead of creating a duplicate identity', async () => {
    // One person = one identity = one aggregate balance. Creating a second
    // "Ксенія" would split her balance, which is the bug the entity fixes.
    partnerItems = [{ id: 'partner-1', name: 'Ксенія', is_active: true }]
    render(<PartnerConfigTab shopId="shop-1" />)
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: '  ксенія  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Add/i }))

    await waitFor(() => expect(upsertMutateAsync).toHaveBeenCalled())
    expect(createPartner).not.toHaveBeenCalled()
    expect(upsertMutateAsync.mock.calls[0][0].partnerId).toBe('partner-1')
  })

  it('refuses to add without a name or with an out-of-range percent', () => {
    render(<PartnerConfigTab shopId="shop-1" />)
    expect(screen.getByRole('button', { name: /Add/i })).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Олег' } })
    expect(screen.getByRole('button', { name: /Add/i })).toBeEnabled()

    fireEvent.change(screen.getByLabelText('%'), { target: { value: '120' } })
    expect(screen.getByRole('button', { name: /Add/i })).toBeDisabled()
    expect(screen.getByText(/between 0 and 100/i)).toBeInTheDocument()
  })

  it('saves a percent edit on blur and rejects an invalid one', () => {
    configItems = [CONFIG]
    render(<PartnerConfigTab shopId="shop-1" />)
    const input = screen.getByLabelText('Percent for Ксенія')

    fireEvent.change(input, { target: { value: '35' } })
    fireEvent.blur(input)
    expect(upsertMutate).toHaveBeenCalledWith({
      partnerId: 'partner-1',
      payload: {
        percent: '35',
        basis: 'turnover',
        settlement_currency: 'USD',
        is_active: true,
      },
    })

    upsertMutate.mockClear()
    fireEvent.change(input, { target: { value: '0' } })
    fireEvent.blur(input)
    expect(upsertMutate).not.toHaveBeenCalled()
  })

  it('removes a partner from the shop', () => {
    configItems = [CONFIG]
    render(<PartnerConfigTab shopId="shop-1" />)
    fireEvent.click(screen.getByRole('button', { name: /Remove Ксенія/i }))
    expect(removeMutate).toHaveBeenCalledWith('partner-1')
  })

  it('states that a rate change does not re-price existing settlements', () => {
    render(<PartnerConfigTab shopId="shop-1" />)
    expect(
      screen.getByText(/never re-prices a settlement that already exists/i),
    ).toBeInTheDocument()
  })
})
