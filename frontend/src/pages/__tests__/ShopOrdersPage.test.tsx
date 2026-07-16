import React from 'react';
import { render, act, cleanup } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { afterEach } from 'vitest';

import ShopOrdersPage from '../ShopOrdersPage';
import type { OrderListFilters } from '@/types/order';

const h = vi.hoisted(() => ({
  lastFilters: undefined as OrderListFilters | undefined,
}));

// Passthrough the page chrome (ShellPage pulls in useAuth + AppLayout) so the test
// stays focused on the shopId param -> shop filter wiring.
vi.mock('../ShellPage', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/hooks/useShops', () => ({
  useShops: () => ({
    data: [
      { id: 'shop-a', name: 'A' },
      { id: 'shop-b', name: 'B' },
    ],
    isLoading: false,
  }),
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
            shop_name: 'A',
            customer_name: 'Jane Doe',
            customer_id: 'cust-0001',
            title: 'Leather wallet',
            total_price: 120,
            currency: 'usd',
            ordered_at: new Date().toISOString(),
            status: 'new',
          },
        ],
        total: 1,
        page: 1,
        limit: 50,
        pages: 1,
      },
      isLoading: false,
    };
  },
  useUpdateOrderStatus: () => ({ mutate: vi.fn() }),
  useBulkUpdateOrderStatus: () => ({ mutate: vi.fn(), isPending: false }),
}));

afterEach(() => {
  cleanup();
  h.lastFilters = undefined;
});

describe('ShopOrdersPage shop switching', () => {
  it('re-filters the orders query when the shop route param changes', async () => {
    const router = createMemoryRouter(
      [{ path: '/shops/:shopId/orders', element: <ShopOrdersPage /> }],
      { initialEntries: ['/shops/shop-a/orders'] },
    );

    render(<RouterProvider router={router} />);

    // Filtered to the initial shop.
    expect(h.lastFilters?.shop_id).toBe('shop-a');

    // Same-route param change: the OrdersLayout remount (key={shopId}) re-seeds
    // its shop filter from the new param instead of keeping the stale one.
    await act(async () => {
      await router.navigate('/shops/shop-b/orders');
    });

    expect(h.lastFilters?.shop_id).toBe('shop-b');
  });
});
