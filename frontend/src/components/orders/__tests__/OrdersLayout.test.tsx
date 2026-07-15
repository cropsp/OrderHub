import React from 'react';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach } from 'vitest';

import OrdersLayout from '../OrdersLayout';
import type { OrderListFilters } from '@/types/order';

const h = vi.hoisted(() => ({
  lastFilters: undefined as OrderListFilters | undefined,
  mockPages: 3,
  bulkMutate: vi.fn(),
}));

vi.mock('@/hooks/useShops', () => ({
  useShops: () => ({ data: [] }),
}));

// Stubbed so the bulk-bar's Radix Select is out of the picture — this file covers
// OrdersLayout's wiring (selection → confirm → mutation). The real Select is
// exercised in the browser smoke, mirroring the ORD-UX-1 submenu precedent.
vi.mock('../BulkStatusBar', () => ({
  default: ({
    count,
    onClear,
    onApply,
  }: {
    count: number;
    onClear: () => void;
    onApply: (status: string) => void;
  }) => (
    <div>
      <span>{count} selected</span>
      <button onClick={() => onApply('shipped')}>stub-pick-shipped</button>
      <button onClick={onClear}>stub-clear</button>
    </div>
  ),
}));

vi.mock('@/hooks/useOrders', () => ({
  useOrders: (filters: OrderListFilters) => {
    h.lastFilters = filters;
    return {
      data: {
        items: [
          {
            id: 'order-1',
            external_id: 'EX-1',
            shop_name: 'Lamamarka',
            customer_name: 'Jane Doe',
            customer_id: 'cust-0001',
            title: 'Leather wallet',
            total_price: 120,
            currency: 'usd',
            ordered_at: new Date().toISOString(),
            status: 'new',
          },
        ],
        total: 150,
        page: filters.page ?? 1,
        limit: 50,
        pages: h.mockPages,
      },
      isLoading: false,
    };
  },
  useUpdateOrderStatus: () => ({ mutate: vi.fn() }),
  useBulkUpdateOrderStatus: () => ({ mutate: h.bulkMutate, isPending: false }),
}));

afterEach(() => {
  cleanup();
  h.lastFilters = undefined;
  h.bulkMutate.mockReset();
});

describe('OrdersLayout pagination', () => {
  it('disables both controls on a single-page result', () => {
    h.mockPages = 1;
    render(
      <MemoryRouter>
        <OrdersLayout />
      </MemoryRouter>,
    );

    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
    expect(screen.getByText(/page 1 of 1/i)).toBeInTheDocument();
  });

  it('advances the page on Next and resets to 1 when a filter changes', () => {
    h.mockPages = 3;
    render(
      <MemoryRouter>
        <OrdersLayout />
      </MemoryRouter>,
    );

    // Starts on page 1.
    expect(h.lastFilters?.page).toBe(1);
    expect(h.lastFilters?.limit).toBe(50);

    // Next advances the requested page.
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    expect(h.lastFilters?.page).toBe(2);

    // Changing the search filter resets the page back to 1.
    fireEvent.change(
      screen.getByPlaceholderText('Search by Order ID, Customer or Product...'),
      { target: { value: 'abc' } },
    );
    expect(h.lastFilters?.page).toBe(1);
    expect(h.lastFilters?.search).toBe('abc');
  });
});

describe('OrdersLayout bulk selection', () => {
  const renderLayout = () => {
    h.mockPages = 3;
    render(
      <MemoryRouter>
        <OrdersLayout />
      </MemoryRouter>,
    );
  };

  it('shows the bulk bar only once a row is selected', () => {
    renderLayout();

    expect(screen.queryByText(/1 selected/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Select order EX-1'));

    expect(screen.getByText('1 selected')).toBeInTheDocument();
  });

  it('applies the picked status to the selected ids after confirmation', () => {
    renderLayout();
    fireEvent.click(screen.getByLabelText('Select order EX-1'));
    fireEvent.click(screen.getByText('stub-pick-shipped'));

    // Confirmation is required before anything is sent.
    expect(h.bulkMutate).not.toHaveBeenCalled();
    expect(screen.getByText(/set 1 order to shipped\?/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));

    expect(h.bulkMutate).toHaveBeenCalledTimes(1);
    expect(h.bulkMutate.mock.calls[0][0]).toEqual({
      orderIds: ['order-1'],
      status: 'shipped',
    });
  });

  it('clears the selection once the batch succeeds', () => {
    h.bulkMutate.mockImplementation((_vars, opts) =>
      opts.onSuccess({ updated: 1, unchanged: 0, skipped: [], warnings: [] }),
    );
    renderLayout();
    fireEvent.click(screen.getByLabelText('Select order EX-1'));
    fireEvent.click(screen.getByText('stub-pick-shipped'));
    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));

    expect(screen.queryByText(/1 selected/)).not.toBeInTheDocument();
  });

  it('drops the selection when the status tab or page changes', () => {
    renderLayout();

    fireEvent.click(screen.getByLabelText('Select order EX-1'));
    expect(screen.getByText('1 selected')).toBeInTheDocument();

    // Status tab — the ids belong to the previous result set.
    fireEvent.click(screen.getByRole('button', { name: /^new$/i }));
    expect(screen.queryByText(/1 selected/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Select order EX-1'));
    expect(screen.getByText('1 selected')).toBeInTheDocument();

    // Pager.
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    expect(screen.queryByText(/1 selected/)).not.toBeInTheDocument();
  });
});
