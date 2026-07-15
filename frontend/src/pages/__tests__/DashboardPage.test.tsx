import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import {
  endOfMonth,
  endOfYear,
  format,
  startOfMonth,
  startOfYear,
} from 'date-fns';

import DashboardPage from '../DashboardPage';
import type { DashboardResponse } from '@/types/dashboard';

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

const mockDashboard = vi.fn();
vi.mock('@/hooks/useDashboard', () => ({
  useDashboard: (...args: unknown[]) => mockDashboard(...args),
}));

function buildDashboardResponse(
  overrides: Partial<DashboardResponse> = {},
): DashboardResponse {
  return {
    stats: {
      orders_by_status: { new: 3, waiting_info: 2 },
      total_orders: 5,
      attention_needed_count: 5,
    },
    revenue_by_currency: [],
    daily_revenue_trend: [],
    orders_by_shop: [],
    low_stock_packaging_count: 0,
    unallocated_overhead: [],
    ...overrides,
  };
}

const mockOrders = vi.fn();
vi.mock('@/hooks/useOrders', () => ({
  useOrders: (...args: unknown[]) => {
    mockOrders(...args);
    return {
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
    };
  },
}));

vi.mock('@/components/dashboard/RevenueChart', () => ({
  default: () => <div>Revenue Chart</div>,
}));

vi.mock('@/components/dashboard/ShopChart', () => ({
  default: () => <div>Shop Chart</div>,
}));

function renderDashboard() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  );
}

describe('DashboardPage smoke test', () => {
  beforeEach(() => {
    mockDashboard.mockReset();
  });

  it('renders dashboard widgets without crashing', () => {
    mockDashboard.mockReturnValue({
      data: buildDashboardResponse(),
      isLoading: false,
      error: null,
    });
    renderDashboard();

    expect(screen.getByText('Executive Overview')).toBeInTheDocument();
    expect(screen.getByText('Priority triage')).toBeInTheDocument();
    expect(screen.getByText('Telemetry feed')).toBeInTheDocument();
  });

  it('renders Workshop overhead card when unallocated_overhead has a non-zero amount', () => {
    mockDashboard.mockReturnValue({
      data: buildDashboardResponse({
        unallocated_overhead: [{ currency: 'UAH', amount: 300 }],
      }),
      isLoading: false,
      error: null,
    });
    renderDashboard();

    expect(
      screen.getByTestId('unallocated-overhead-card'),
    ).toBeInTheDocument();
    expect(screen.getByText('Workshop overhead (unallocated)')).toBeInTheDocument();
    expect(screen.getByText(/300\.00 UAH/)).toBeInTheDocument();
  });

  it('hides Workshop overhead card when unallocated_overhead is empty', () => {
    mockDashboard.mockReturnValue({
      data: buildDashboardResponse({ unallocated_overhead: [] }),
      isLoading: false,
      error: null,
    });
    renderDashboard();

    expect(
      screen.queryByTestId('unallocated-overhead-card'),
    ).not.toBeInTheDocument();
  });
});

describe('DashboardPage period selector (DASH-PERIOD)', () => {
  const iso = (d: Date) => format(d, 'yyyy-MM-dd');

  beforeEach(() => {
    mockDashboard.mockReset();
    mockOrders.mockClear();
    localStorage.clear();
    mockDashboard.mockReturnValue({
      data: buildDashboardResponse(),
      isLoading: false,
      error: null,
    });
  });

  it('defaults to This Month and fetches that window', () => {
    renderDashboard();

    expect(screen.getByRole('button', { name: 'This Month' })).toBeInTheDocument();
    const now = new Date();
    expect(mockDashboard).toHaveBeenLastCalledWith(
      undefined,
      iso(startOfMonth(now)),
      iso(endOfMonth(now)),
    );
  });

  it('refetches with the new window when the preset changes', () => {
    renderDashboard();
    fireEvent.click(screen.getByRole('button', { name: 'This Year' }));

    const now = new Date();
    expect(mockDashboard).toHaveBeenLastCalledWith(
      undefined,
      iso(startOfYear(now)),
      iso(endOfYear(now)),
    );
  });

  it('never scopes the attention queue by the period', () => {
    renderDashboard();
    fireEvent.click(screen.getByRole('button', { name: 'This Year' }));

    // The attention/recent lists are the "what needs action now" queue — they
    // stay live, so no useOrders call may carry date params.
    expect(mockOrders).toHaveBeenCalled();
    for (const [params] of mockOrders.mock.calls) {
      expect(params).not.toHaveProperty('start_date');
      expect(params).not.toHaveProperty('end_date');
    }
  });

  it('remembers its own preset, not the Finance page key', () => {
    renderDashboard();
    fireEvent.click(screen.getByRole('button', { name: 'This Year' }));

    expect(localStorage.getItem('orderhub:dashboard:lastPreset')).toBe('this_year');
    expect(localStorage.getItem('orderhub:shopFinance:lastPreset')).toBeNull();
  });
});
