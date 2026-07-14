import React from 'react';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach } from 'vitest';

import OrdersLayout from '../OrdersLayout';
import type { OrderListFilters } from '@/types/order';

const h = vi.hoisted(() => ({
  lastFilters: undefined as OrderListFilters | undefined,
  mockPages: 3,
}));

vi.mock('@/hooks/useShops', () => ({
  useShops: () => ({ data: [] }),
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
}));

afterEach(() => {
  cleanup();
  h.lastFilters = undefined;
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
