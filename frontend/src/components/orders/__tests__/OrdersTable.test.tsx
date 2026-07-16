import React from 'react';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach } from 'vitest';

import OrdersTable from '../OrdersTable';
import type { OrderListItem } from '@/types/order';

const mutateMock = vi.fn();
const h = vi.hoisted(() => ({ updateStatusCalls: 0 }));

vi.mock('@/hooks/useOrders', () => ({
  useUpdateOrderStatus: () => {
    h.updateStatusCalls += 1;
    return { mutate: mutateMock };
  },
}));

const order = {
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
} as unknown as OrderListItem;

const secondOrder = { ...order, id: 'order-2', external_id: 'EX-2' } as OrderListItem;

function renderTable(props: Partial<React.ComponentProps<typeof OrdersTable>> = {}) {
  const merged = {
    orders: [order],
    selectedIds: new Set<string>(),
    onToggleOne: vi.fn(),
    onToggleAll: vi.fn(),
    ...props,
  };
  render(
    <MemoryRouter>
      <OrdersTable {...merged} />
    </MemoryRouter>,
  );
  return merged;
}

afterEach(cleanup);

describe('OrdersTable inline status change', () => {
  it('renders the order row and wires the status-update hook', () => {
    h.updateStatusCalls = 0;
    renderTable();

    // Row content renders.
    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText('Leather wallet')).toBeInTheDocument();

    // The inline status-change hook is integrated into the table.
    expect(h.updateStatusCalls).toBeGreaterThan(0);

    // The row-actions trigger is present.
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('shows the recipient (shipping_name) instead of the Etsy buyer handle', () => {
    const recipientOrder = {
      ...order,
      shipping_name: 'Paula Borowsky',
      customer_name: 'E B (qzp7sdny)',
    } as unknown as OrderListItem;

    renderTable({ orders: [recipientOrder] });

    expect(screen.getByText('Paula Borowsky')).toBeInTheDocument();
    expect(screen.queryByText('E B (qzp7sdny)')).not.toBeInTheDocument();
  });
});

describe('OrdersTable bulk selection', () => {
  it('toggles a single row through onToggleOne', () => {
    const { onToggleOne } = renderTable();

    fireEvent.click(screen.getByLabelText('Select order EX-1'));

    expect(onToggleOne).toHaveBeenCalledWith('order-1');
  });

  it('selects every rendered row through onToggleAll', () => {
    const { onToggleAll } = renderTable({ orders: [order, secondOrder] });

    fireEvent.click(screen.getByLabelText('Select all orders on this page'));

    expect(onToggleAll).toHaveBeenCalledWith(true);
  });

  it('reflects selection state and shows indeterminate on a partial page', () => {
    renderTable({
      orders: [order, secondOrder],
      selectedIds: new Set(['order-1']),
    });

    const selectAll = screen.getByLabelText(
      'Select all orders on this page',
    ) as HTMLInputElement;
    expect((screen.getByLabelText('Select order EX-1') as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText('Select order EX-2') as HTMLInputElement).checked).toBe(false);
    expect(selectAll.checked).toBe(false);
    expect(selectAll.indeterminate).toBe(true);
  });

  it('checks the header box when every row on the page is selected', () => {
    renderTable({
      orders: [order, secondOrder],
      selectedIds: new Set(['order-1', 'order-2']),
    });

    const selectAll = screen.getByLabelText(
      'Select all orders on this page',
    ) as HTMLInputElement;
    expect(selectAll.checked).toBe(true);
    expect(selectAll.indeterminate).toBe(false);
  });
});
