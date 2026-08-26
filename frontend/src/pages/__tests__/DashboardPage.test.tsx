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

// Mutable so the role can be swapped per test — WB-ALERTS-1 hides the parcel
// alerts block from DESIGNERs, whom the dashboard route does let in.
const mockUser = {
  id: 'user-1',
  email: 'owner@orderhub.dev',
  full_name: 'Owner',
  role: 'owner',
  is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: mockUser,
    isLoading: false,
    isAuthenticated: true,
    logout: vi.fn(),
    login: vi.fn(),
  }),
}));

// Without this the new useParcelAlerts hook fires a real query and every test
// in this file dies on "No QueryClient set".
const mockParcelAlerts = vi.fn();
// Quiet by default and never reset — every test in this file is about the
// widgets around it, and an empty cases block renders one silent line.
const mockOpenCases = vi.fn(() => ({
  data: { in_progress: [], waiting: [] },
  isLoading: false,
}));
const mockDismissAlert = vi.fn();
vi.mock('@/hooks/useWesternBid', () => ({
  useParcelAlerts: (...args: unknown[]) => mockParcelAlerts(...args),
  useDismissParcelAlert: () => ({
    mutate: mockDismissAlert,
    isPending: false,
    variables: undefined,
  }),
}));

// CASE-1: the page gained a cases block beside the parcel alerts. Mocked for
// the same reason every other hook here is — this file is a page smoke test,
// not a query-layer test.
vi.mock('@/hooks/useOrderCases', () => ({
  useOpenCases: (...args: unknown[]) => mockOpenCases(...args),
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

function quietAlerts() {
  mockParcelAlerts.mockReturnValue({
    data: { alerts: [], synced_at: '2026-08-20T09:14:00Z' },
    isLoading: false,
  });
}

describe('DashboardPage smoke test', () => {
  beforeEach(() => {
    mockDashboard.mockReset();
    mockUser.role = 'owner';
    mockParcelAlerts.mockReset();
    quietAlerts();
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
    mockUser.role = 'owner';
    mockParcelAlerts.mockReset();
    quietAlerts();
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

describe('DashboardPage parcel alerts (WB-ALERTS-1)', () => {
  const alert = {
    id: 'alert-1',
    kind: 'overdue_long',
    detail: 'Прострочено 12.7 дн.',
    shipment_id: 'ship-1',
    tracking_number: '59500007044916',
    tracking_numbers: [],
    recipient_name: 'Jane Doe',
    carrier: 'NovaPost',
    raised_at: new Date().toISOString(),
    age_days: 2.0,
    dismissed_at: null,
    dismissed_by_id: null,
  };

  beforeEach(() => {
    mockDashboard.mockReset();
    mockParcelAlerts.mockReset();
    mockDismissAlert.mockReset();
    mockUser.role = 'owner';
    localStorage.clear();
    mockDashboard.mockReturnValue({
      data: buildDashboardResponse(),
      isLoading: false,
      error: null,
    });
    quietAlerts();
  });

  it('shows a quiet all-clear line rather than nothing when there are no alerts', () => {
    renderDashboard();

    // "all clear" and "the generator is broken" must not look identical, which
    // is why the empty state still names the sync time.
    expect(screen.getByTestId('parcel-alerts-card')).toBeInTheDocument();
    expect(screen.getByText(/Посилки: все гаразд/)).toBeInTheDocument();
  });

  it('renders a prominent block with a count when alerts exist', () => {
    mockParcelAlerts.mockReturnValue({
      data: { alerts: [alert], synced_at: '2026-08-20T09:14:00Z' },
      isLoading: false,
    });
    renderDashboard();

    expect(screen.getByText('Посилки — потребують уваги')).toBeInTheDocument();
    expect(screen.getByText('Прострочено 12.7 дн.')).toBeInTheDocument();
    expect(screen.getByText('59500007044916')).toBeInTheDocument();
  });

  it('dismisses through the mutation when Опрацьовано is clicked', () => {
    mockParcelAlerts.mockReturnValue({
      data: { alerts: [alert], synced_at: null },
      isLoading: false,
    });
    renderDashboard();

    fireEvent.click(screen.getByRole('button', { name: 'Опрацьовано' }));

    expect(mockDismissAlert).toHaveBeenCalledWith('alert-1');
  });

  it('hides the block from a designer, who would 403 on the endpoint', () => {
    mockUser.role = 'designer';
    renderDashboard();

    expect(screen.queryByTestId('parcel-alerts-card')).not.toBeInTheDocument();
    // The query must not fire either — `enabled` is what gates it.
    expect(mockParcelAlerts).toHaveBeenCalledWith(false);
  });

  it('never scopes the alerts by the dashboard period', () => {
    renderDashboard();
    fireEvent.click(screen.getByRole('button', { name: 'This Year' }));

    // Alerts are an attention queue, like the order triage list above them —
    // they stay live and take no date arguments at all.
    expect(mockParcelAlerts).toHaveBeenCalled();
    for (const args of mockParcelAlerts.mock.calls) {
      expect(args).toEqual([true]);
    }
  });
});
