import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import OrderDetailView from '../OrderDetailView';

/**
 * CASE-1-fix — container wiring for the order card.
 *
 * This file exists because CASE-1 shipped `DetailCases` wired into
 * `OrderDetailPanel`, which has had no importers since `15d7b5d`. Every cases
 * test passed and the section rendered for nobody. Component tests cannot catch
 * that; only a test that asserts the live container composes it can.
 *
 * The heavy siblings are stubbed — this is about what `OrderDetailView` renders
 * and for whom, not about what they render.
 */

const controller = vi.fn();
vi.mock('@/hooks/useOrderDetailController', () => ({
  useOrderDetailController: (...args: unknown[]) => controller(...args),
}));

// DetailCases renders for real — the testid asserted below is its own
// (DetailCases.tsx), so a broken import would fail this test rather than pass a
// stub. Only its queries are mocked.
vi.mock('@/hooks/useOrderCases', () => ({
  useOrderCases: () => ({ data: [], isLoading: false }),
  useCreateCase: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateCase: () => ({ mutate: vi.fn(), isPending: false }),
  useAddCaseNote: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('../AttachmentManager', () => ({ default: () => <div /> }));
vi.mock('../detail/DetailHeader', () => ({ DetailHeader: () => <div /> }));
vi.mock('../detail/DetailItems', () => ({ DetailItems: () => <div /> }));
vi.mock('../detail/DetailNotes', () => ({
  DetailCustomizationInfo: () => <div />,
  DetailInternalNotes: () => <div />,
}));
vi.mock('../detail/DetailCustomer', () => ({ DetailCustomer: () => <div /> }));
vi.mock('../detail/DetailLogistics', () => ({ DetailLogistics: () => <div /> }));
vi.mock('../detail/DetailFinance', () => ({ DetailFinance: () => <div /> }));
vi.mock('../detail/DetailTimeline', () => ({ DetailTimeline: () => <div /> }));

function setController(overrides: Record<string, unknown> = {}) {
  controller.mockReturnValue({
    order: { id: 'order-1', status: 'new' },
    isLoading: false,
    isOwner: false,
    isManager: false,
    canManageShipping: false,
    canViewCosts: false,
    saveStatus: 'idle',
    handleUpdate: vi.fn(),
    handleStatusChange: vi.fn(),
    handleGenerateTTN: vi.fn(),
    handleDeleteTTN: vi.fn(),
    isTTNPending: false,
    handleAddItem: vi.fn(),
    handleUpdateItem: vi.fn(),
    handleDeleteItem: vi.fn(),
    ...overrides,
  });
}

function renderView() {
  return render(
    <MemoryRouter>
      <OrderDetailView orderId="order-1" />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('OrderDetailView cases section (CASE-1)', () => {
  it('renders the cases section for a manager', () => {
    setController({ isManager: true });
    renderView();

    expect(screen.getByTestId('detail-cases')).toBeInTheDocument();
  });

  it('renders the cases section for an owner', () => {
    setController({ isOwner: true });
    renderView();

    expect(screen.getByTestId('detail-cases')).toBeInTheDocument();
  });

  it('hides the cases section from a designer', () => {
    // Task rule 5: DESIGNER gets nothing in v1. The endpoints 403 as well, but
    // the section must not render a permanently-loading box either.
    setController();
    renderView();

    expect(screen.queryByTestId('detail-cases')).not.toBeInTheDocument();
  });
});
