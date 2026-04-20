import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import DashboardPage from '../DashboardPage';

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
}));

vi.mock('@/hooks/useShops', () => ({
  useShops: () => ({ data: [], isLoading: false }),
}));

vi.mock('@/hooks/useDashboard', () => ({
  useDashboard: () => ({
    data: {
      stats: {
        orders_by_status: { new: 3, waiting_info: 2 },
        total_orders: 5,
        attention_needed_count: 5,
      },
      revenue_by_currency: [],
      daily_revenue_trend: [],
      orders_by_shop: [],
    },
    isLoading: false,
    error: null,
  }),
}));

vi.mock('@/hooks/useOrders', () => ({
  useOrders: () => ({
    data: {
      items: [
        {
          id: 'ord-1',
          external_id: '1001',
          title: 'Custom Wallet',
          status: 'new',
          ordered_at: new Date().toISOString(),
          shop_name: 'Main Shop',
        },
      ],
    },
    isLoading: false,
  }),
}));

vi.mock('@/components/dashboard/RevenueChart', () => ({
  default: () => <div>Revenue Chart</div>,
}));

vi.mock('@/components/dashboard/ShopChart', () => ({
  default: () => <div>Shop Chart</div>,
}));

describe('DashboardPage smoke test', () => {
  it('renders dashboard widgets without crashing', () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );

    expect(screen.getByText('Dashboard Overview')).toBeInTheDocument();
    expect(screen.getByText('Attention List')).toBeInTheDocument();
    expect(screen.getByText('Recent Activity')).toBeInTheDocument();
  });
});
