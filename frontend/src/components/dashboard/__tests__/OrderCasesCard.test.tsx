import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import OrderCasesCard from '../OrderCasesCard';
import type { OpenCaseRow, OpenCasesResponse } from '@/types/orderCase';

/**
 * CASE-1 — the dashboard cases block.
 *
 * Pure props, no providers: the two groups arrive already split and already
 * ordered, because "overdue" has exactly one definition and it lives in
 * `order_case_service`. This component must not re-derive it — only the red
 * treatment is its own, and that is what these tests pin.
 */

const PAST = '2020-01-02T10:00:00Z';
const FUTURE = '2999-01-02T10:00:00Z';

function buildRow(overrides: Partial<OpenCaseRow> = {}): OpenCaseRow {
  return {
    id: 'case-1',
    order_id: 'order-1',
    case_type: 'return',
    title: 'Повернулась до відправника',
    status: 'in_progress',
    next_action: 'Уточнити адресу',
    due_at: FUTURE,
    owner_id: null,
    owner_name: 'Оксана',
    created_at: '2026-08-20T09:00:00Z',
    order_number: '91890_1816',
    order_external_id: '5551212',
    customer_name: 'Jane Doe',
    shop_id: 'shop-1',
    shop_name: 'Lamamarka',
    ...overrides,
  };
}

function buildCases(overrides: Partial<OpenCasesResponse> = {}): OpenCasesResponse {
  return { in_progress: [buildRow()], waiting: [], ...overrides };
}

function renderCard(
  props: Partial<React.ComponentProps<typeof OrderCasesCard>> = {},
) {
  return render(
    <MemoryRouter>
      <OrderCasesCard cases={buildCases()} isLoading={false} {...props} />
    </MemoryRouter>,
  );
}

describe('OrderCasesCard', () => {
  it('says all-clear quietly instead of rendering an empty loud box', () => {
    renderCard({ cases: { in_progress: [], waiting: [] } });

    expect(
      screen.getByText('Питання по замовленнях: немає відкритих'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('order-case-row')).not.toBeInTheDocument();
  });

  it('tolerates an undefined payload the same way as an empty one', () => {
    // The query can be disabled (DESIGNER) or still settling; neither is an
    // error state and neither should throw.
    renderCard({ cases: undefined });

    expect(
      screen.getByText('Питання по замовленнях: немає відкритих'),
    ).toBeInTheDocument();
  });

  it('counts both groups in the header badge', () => {
    renderCard({
      cases: {
        in_progress: [buildRow({ id: 'a' }), buildRow({ id: 'b' })],
        waiting: [buildRow({ id: 'c', status: 'waiting' })],
      },
    });

    expect(screen.getByTestId('order-cases-count')).toHaveTextContent('3');
  });

  it('renders the two groups under their own headings', () => {
    renderCard({
      cases: {
        in_progress: [buildRow({ id: 'a', title: 'Робимо' })],
        waiting: [buildRow({ id: 'b', title: 'Чекаємо на клієнта', status: 'waiting' })],
      },
    });

    expect(screen.getByText('В роботі')).toBeInTheDocument();
    expect(screen.getByText('Чекаємо')).toBeInTheDocument();
    expect(screen.getByText('Робимо')).toBeInTheDocument();
    expect(screen.getByText('Чекаємо на клієнта')).toBeInTheDocument();
  });

  it('omits a group heading entirely when that group is empty', () => {
    renderCard({ cases: { in_progress: [buildRow()], waiting: [] } });

    expect(screen.getByText('В роботі')).toBeInTheDocument();
    expect(screen.queryByText('Чекаємо')).not.toBeInTheDocument();
  });

  it('marks an overdue case red and leaves a future deadline plain', () => {
    renderCard({
      cases: {
        in_progress: [buildRow({ id: 'late', due_at: PAST })],
        waiting: [buildRow({ id: 'soon', due_at: FUTURE, status: 'waiting' })],
      },
    });

    const [lateRow, soonRow] = screen.getAllByTestId('order-case-row');
    expect(within(lateRow).getByTestId('order-case-due').className).toContain(
      'text-red-400',
    );
    expect(within(soonRow).getByTestId('order-case-due').className).not.toContain(
      'text-red-400',
    );
  });

  it('treats a case with no deadline as not overdue', () => {
    renderCard({ cases: { in_progress: [buildRow({ due_at: null })], waiting: [] } });

    const due = screen.getByTestId('order-case-due');
    expect(due).toHaveTextContent('без дедлайну');
    expect(due.className).not.toContain('text-red-400');
  });

  it('falls back to the external id when an order has no order_number', () => {
    renderCard({
      cases: {
        in_progress: [buildRow({ order_number: null, order_external_id: '5551212' })],
        waiting: [],
      },
    });

    expect(screen.getByText('5551212')).toBeInTheDocument();
  });

  it('renders an unknown case_type rather than crashing', () => {
    // The server owns this vocabulary and may grow it before the frontend
    // ships — the same stance ParcelAlertsCard takes for alert kinds.
    renderCard({
      cases: { in_progress: [buildRow({ case_type: 'customs_hold' })], waiting: [] },
    });

    expect(screen.getByText('customs_hold')).toBeInTheDocument();
  });

  it('collapses and expands on the header toggle', () => {
    renderCard();

    expect(screen.getByTestId('order-case-row')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { expanded: true }));
    expect(screen.queryByTestId('order-case-row')).not.toBeInTheDocument();
  });

  it('shows a skeleton while loading', () => {
    renderCard({ isLoading: true });

    expect(screen.queryByTestId('order-cases-card')).not.toBeInTheDocument();
    expect(screen.queryByTestId('order-case-row')).not.toBeInTheDocument();
  });
});
