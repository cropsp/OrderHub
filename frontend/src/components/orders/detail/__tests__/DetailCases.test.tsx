import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';

import { DetailCases } from '../DetailCases';
import type { OrderCase } from '@/types/orderCase';

/**
 * CASE-1 — the order-card cases section.
 *
 * Hooks are mocked module-level (the repo's page-test style) so this covers
 * what the component itself decides: which rows render, how a system note reads
 * differently from a human one, and what each control sends.
 */

const createMutate = vi.fn();
const updateMutate = vi.fn();
const addNoteMutate = vi.fn();
const useOrderCasesMock = vi.fn();

vi.mock('@/hooks/useOrderCases', () => ({
  useOrderCases: (...args: unknown[]) => useOrderCasesMock(...args),
  useCreateCase: () => ({ mutate: createMutate, isPending: false }),
  useUpdateCase: () => ({ mutate: updateMutate, isPending: false }),
  useAddCaseNote: () => ({ mutate: addNoteMutate, isPending: false }),
}));

const PAST = '2020-01-02T10:00:00Z';

function buildCase(overrides: Partial<OrderCase> = {}): OrderCase {
  return {
    id: 'case-1',
    order_id: 'order-1',
    case_type: 'return',
    title: 'Повернулась до відправника',
    status: 'in_progress',
    next_action: 'Уточнити адресу',
    due_at: null,
    owner_id: null,
    owner_name: null,
    created_by_id: 'user-1',
    created_by_name: 'Оксана',
    resolved_at: null,
    resolution_note: null,
    created_at: '2026-08-20T09:00:00Z',
    updated_at: '2026-08-20T09:00:00Z',
    notes: [],
    ...overrides,
  };
}

function setCases(cases: OrderCase[], isLoading = false) {
  useOrderCasesMock.mockReturnValue({ data: cases, isLoading });
}

beforeEach(() => {
  vi.clearAllMocks();
  setCases([buildCase()]);
});

describe('DetailCases', () => {
  it('says it quietly when an order has no cases', () => {
    setCases([]);
    render(<DetailCases orderId="order-1" />);

    expect(
      screen.getByText('Питань немає — із цим замовленням усе спокійно'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('case-row')).not.toBeInTheDocument();
  });

  it('lists a case with its type label and next action', () => {
    render(<DetailCases orderId="order-1" />);

    expect(screen.getByText('Повернення')).toBeInTheDocument();
    expect(screen.getByText('Повернулась до відправника')).toBeInTheDocument();
    expect(screen.getByText('→ Уточнити адресу')).toBeInTheDocument();
  });

  it('counts only non-resolved cases in the header badge', () => {
    setCases([
      buildCase({ id: 'a' }),
      buildCase({ id: 'b', status: 'resolved', resolved_at: PAST }),
    ]);
    render(<DetailCases orderId="order-1" />);

    // Two rows listed (resolved cases stay readable forever)...
    expect(screen.getAllByTestId('case-row')).toHaveLength(2);
    // ...but the badge counts the one that still needs doing.
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('styles a system note apart from a human comment', () => {
    setCases([
      buildCase({
        notes: [
          {
            id: 'n1',
            kind: 'comment',
            text: 'Написав клієнту',
            created_at: '2026-08-20T10:00:00Z',
            author_id: 'u1',
            author_name: 'Оксана',
          },
          {
            id: 'n2',
            kind: 'system',
            text: 'Статус: В роботі → Чекаємо',
            created_at: '2026-08-20T11:00:00Z',
            author_id: 'u1',
            author_name: 'Оксана',
          },
        ],
      }),
    ]);
    render(<DetailCases orderId="order-1" />);

    fireEvent.click(screen.getByRole('button', { expanded: false }));

    // The discriminator is the `kind` column — not a prefix parsed out of text.
    expect(screen.getByTestId('case-note-comment')).toHaveTextContent(
      'Написав клієнту',
    );
    expect(screen.getByTestId('case-note-system')).toHaveTextContent(
      'Статус: В роботі → Чекаємо',
    );
  });

  it('attributes a system note to the human who caused it', () => {
    setCases([
      buildCase({
        notes: [
          {
            id: 'n2',
            kind: 'system',
            text: 'Статус: В роботі → Чекаємо',
            created_at: '2026-08-20T11:00:00Z',
            author_id: 'u1',
            author_name: 'Оксана',
          },
        ],
      }),
    ]);
    render(<DetailCases orderId="order-1" />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));

    // Task rule 3: transitions are visible "with author + timestamp".
    expect(screen.getByTestId('case-note-system')).toHaveTextContent('Оксана');
  });

  it('adds a note through the mutation and clears the box', () => {
    render(<DetailCases orderId="order-1" />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));

    const box = screen.getByLabelText('Додати нотатку');
    fireEvent.change(box, { target: { value: 'Клієнт підтвердив адресу' } });
    fireEvent.click(screen.getByText('Додати'));

    expect(addNoteMutate).toHaveBeenCalledWith(
      { caseId: 'case-1', text: 'Клієнт підтвердив адресу' },
      expect.anything(),
    );
  });

  it('refuses to send a whitespace-only note', () => {
    render(<DetailCases orderId="order-1" />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));

    fireEvent.change(screen.getByLabelText('Додати нотатку'), {
      target: { value: '   ' },
    });
    fireEvent.click(screen.getByText('Додати'));

    expect(addNoteMutate).not.toHaveBeenCalled();
  });

  it('sends a status change', () => {
    render(<DetailCases orderId="order-1" />);

    fireEvent.change(screen.getByLabelText('Статус'), {
      target: { value: 'waiting' },
    });

    expect(updateMutate).toHaveBeenCalledWith({
      caseId: 'case-1',
      payload: { status: 'waiting' },
    });
  });

  it('asks for the summary inline, never through a native prompt', () => {
    // The native dialog is off-theme and a browser may suppress it outright,
    // which would resolve cases with a summary nobody was able to type.
    const promptSpy = vi.spyOn(window, 'prompt');
    render(<DetailCases orderId="order-1" />);

    fireEvent.change(screen.getByLabelText('Статус'), {
      target: { value: 'resolved' },
    });

    expect(promptSpy).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Підсумок')).toBeInTheDocument();
    // Picking the status is not yet the decision — confirming is.
    expect(updateMutate).not.toHaveBeenCalled();
    promptSpy.mockRestore();
  });

  it('passes the typed summary along when resolving is confirmed', () => {
    render(<DetailCases orderId="order-1" />);

    fireEvent.change(screen.getByLabelText('Статус'), {
      target: { value: 'resolved' },
    });
    fireEvent.change(screen.getByLabelText('Підсумок'), {
      target: { value: 'Переслали, отримав' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Вирішити' }));

    expect(updateMutate).toHaveBeenCalledWith(
      {
        caseId: 'case-1',
        payload: { status: 'resolved', resolution_note: 'Переслали, отримав' },
      },
      expect.anything(),
    );
  });

  it('still resolves when the summary is left empty', () => {
    // The note is optional; a forced field just gets filled with "ok".
    render(<DetailCases orderId="order-1" />);

    fireEvent.change(screen.getByLabelText('Статус'), {
      target: { value: 'resolved' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Вирішити' }));

    expect(updateMutate).toHaveBeenCalledWith(
      { caseId: 'case-1', payload: { status: 'resolved' } },
      expect.anything(),
    );
  });

  it('dismisses the summary box when another status is picked instead', () => {
    render(<DetailCases orderId="order-1" />);

    fireEvent.change(screen.getByLabelText('Статус'), {
      target: { value: 'resolved' },
    });
    fireEvent.change(screen.getByLabelText('Статус'), {
      target: { value: 'waiting' },
    });

    expect(screen.queryByLabelText('Підсумок')).not.toBeInTheDocument();
    expect(updateMutate).toHaveBeenCalledWith({
      caseId: 'case-1',
      payload: { status: 'waiting' },
    });
  });

  it('cancelling the summary box resolves nothing', () => {
    render(<DetailCases orderId="order-1" />);

    fireEvent.change(screen.getByLabelText('Статус'), {
      target: { value: 'resolved' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Скасувати' }));

    expect(updateMutate).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('Підсумок')).not.toBeInTheDocument();
  });

  it('creates a case from the form', () => {
    render(<DetailCases orderId="order-1" />);

    fireEvent.click(screen.getByText('питання'));
    fireEvent.change(screen.getByLabelText('Заголовок'), {
      target: { value: 'Клієнт лишив 1 зірку' },
    });
    fireEvent.change(screen.getByLabelText('Тип'), {
      target: { value: 'review' },
    });
    fireEvent.click(screen.getByText('Створити'));

    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({ case_type: 'review', title: 'Клієнт лишив 1 зірку' }),
      expect.anything(),
    );
  });

  it('refuses to create a case with an empty title', () => {
    render(<DetailCases orderId="order-1" />);

    fireEvent.click(screen.getByText('питання'));
    fireEvent.click(screen.getByText('Створити'));

    expect(createMutate).not.toHaveBeenCalled();
  });

  it('marks an overdue deadline red but not on a resolved case', () => {
    setCases([
      buildCase({ id: 'late', due_at: PAST }),
      buildCase({
        id: 'done',
        due_at: PAST,
        status: 'resolved',
        resolved_at: PAST,
      }),
    ]);
    render(<DetailCases orderId="order-1" />);

    const [lateRow, doneRow] = screen.getAllByTestId('case-row');
    expect(within(lateRow).getByTestId('case-due').className).toContain(
      'text-red-300',
    );
    // A closed case is never "late" — its deadline stopped mattering.
    expect(within(doneRow).getByTestId('case-due').className).not.toContain(
      'text-red-300',
    );
  });

  it('renders an unknown case_type rather than crashing', () => {
    setCases([buildCase({ case_type: 'customs_hold' })]);
    render(<DetailCases orderId="order-1" />);

    expect(screen.getByText('customs_hold')).toBeInTheDocument();
  });
});
