import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ShopFinancePage from '../ShopFinancePage';
import type { ShopFinanceResponse } from '@/types/finance';

// ShellPage pulls in the full auth + shops stack; stub it down to a passthrough.
vi.mock('../ShellPage', () => ({
  default: ({ children, title }: { children: React.ReactNode; title: string }) => (
    <div>
      <h1>{title}</h1>
      {children}
    </div>
  ),
}));

const mockFinance = vi.fn();
vi.mock('@/hooks/useShopFinance', () => ({
  useShopFinance: (...args: unknown[]) => mockFinance(...args),
}));

// PART-1: PartnerPayoutsSection uses react-query hooks; the section is mounted
// inside ShopFinancePage. Stub it out — this test file targets KPI rendering
// only, and PartnerPayoutsSection has its own dedicated tests.
vi.mock('@/components/finance/PartnerPayoutsSection', () => ({
  default: () => null,
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/shops/abc-123/finance']}>
        <Routes>
          <Route path="/shops/:shopId/finance" element={<ShopFinancePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function buildResponse(overrides: Partial<ShopFinanceResponse> = {}): ShopFinanceResponse {
  return {
    shop_id: 'abc-123',
    shop_name: 'Test Shop',
    period_start_iso: '2026-05-01',
    period_end_iso: '2026-05-14',
    granularity: 'day',
    revenue: {
      current: [
        { currency: 'UAH', amount: 45000 },
        { currency: 'USD', amount: 850 },
      ],
      previous: [{ currency: 'UAH', amount: 40000 }],
      change_percent: 12.5,
    },
    cogs: { current: [], previous: [], change_percent: null },
    fees: { current: [], previous: [], change_percent: null },
    allocated_overhead_expenses: { current: [], previous: [], change_percent: null },
    net_profit: { current: [], previous: [], change_percent: null },
    pipeline_value: { current: [], previous: [], change_percent: null },
    order_count: { current: 12, previous: 10, change_percent: 20.0 },
    aov: { current: [], previous: [], change_percent: null },
    time_series: [
      { date: '2026-05-01', currency: 'UAH', revenue: 1000, net_profit: 400 },
      { date: '2026-05-02', currency: 'UAH', revenue: 1500, net_profit: 600 },
    ],
    diagnostic: {
      orders_missing_cost: 0,
      total_orders_in_period: 12,
      orders_with_computed_cost: 0,
    },
    shipping_net: { current: [], previous: [], change_percent: null },
    ...overrides,
  };
}

describe('ShopFinancePage', () => {
  beforeEach(() => {
    mockFinance.mockReset();
  });

  it('renders both currency lines in the Revenue card', () => {
    mockFinance.mockReturnValue({
      data: buildResponse(),
      isLoading: false,
      error: null,
    });
    renderPage();
    // Multi-currency amounts are joined with \n inside a `whitespace-pre-line` div,
    // so each appears as a separate text node.
    expect(screen.getByText(/45,000\.00 UAH/)).toBeInTheDocument();
    expect(screen.getByText(/850\.00 USD/)).toBeInTheDocument();
  });

  it('renders the diagnostic badge when orders_missing_cost > 0', () => {
    mockFinance.mockReturnValue({
      data: buildResponse({
        diagnostic: { orders_missing_cost: 3, total_orders_in_period: 12 },
      }),
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(screen.getByText(/3 of 12 orders/)).toBeInTheDocument();
    expect(screen.getByText(/Net Profit may be inflated/)).toBeInTheDocument();
  });

  it('hides the diagnostic badge when orders_missing_cost === 0', () => {
    mockFinance.mockReturnValue({
      data: buildResponse(),
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(screen.queryByText(/Net Profit may be inflated/)).not.toBeInTheDocument();
  });

  it('renders the Allocated Overhead card when the API returns a non-zero value', () => {
    mockFinance.mockReturnValue({
      data: buildResponse({
        allocated_overhead_expenses: {
          current: [{ currency: 'UAH', amount: 450 }],
          previous: [],
          change_percent: null,
        },
      }),
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(screen.getByText('Allocated Overhead')).toBeInTheDocument();
    expect(screen.getByText(/450\.00 UAH/)).toBeInTheDocument();
  });

  it('renders the BOM-computed-cost info line when orders_with_computed_cost > 0', () => {
    mockFinance.mockReturnValue({
      data: buildResponse({
        diagnostic: {
          orders_missing_cost: 0,
          total_orders_in_period: 12,
          orders_with_computed_cost: 5,
        },
      }),
      isLoading: false,
      error: null,
    });
    renderPage();
    expect(
      screen.getByText(/5 of 12 orders use BOM-computed cost/),
    ).toBeInTheDocument();
    // The amber "missing cost" warning must NOT render when missing_cost is 0.
    expect(screen.queryByText(/Net Profit may be inflated/)).not.toBeInTheDocument();
  });

  it('renders the chart wrapper when time_series has data and the empty-state placeholder when not', () => {
    mockFinance.mockReturnValue({
      data: buildResponse(),
      isLoading: false,
      error: null,
    });
    const { container, unmount } = renderPage();
    expect(container.querySelector('.recharts-wrapper')).not.toBeNull();
    expect(screen.queryByText('No revenue data')).not.toBeInTheDocument();
    unmount();

    mockFinance.mockReturnValue({
      data: buildResponse({ time_series: [] }),
      isLoading: false,
      error: null,
    });
    const second = renderPage();
    expect(second.container.querySelector('.recharts-wrapper')).toBeNull();
    expect(screen.getByText('No revenue data')).toBeInTheDocument();
  });
});
