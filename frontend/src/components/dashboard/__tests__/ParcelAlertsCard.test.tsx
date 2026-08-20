import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import ParcelAlertsCard from '../ParcelAlertsCard';
import type { ParcelAlert } from '@/types/westernbid';

/**
 * WB-ALERTS-1 — the dashboard alerts block.
 *
 * Pure props, no providers: the component decides nothing about what deserves
 * an alert, so there is nothing to mock. Every kind, threshold and reason
 * string arrives from the server.
 */

function buildAlert(overrides: Partial<ParcelAlert> = {}): ParcelAlert {
  return {
    id: 'alert-1',
    kind: 'overdue_long',
    detail: 'Прострочено 12.7 дн.',
    shipment_id: 'ship-1',
    tracking_number: '59500007044916',
    tracking_numbers: [
      { Identifier: 'NovaPost', TrackingNumber: '59500007044916' },
    ],
    recipient_name: 'Jane Doe',
    carrier: 'NovaPost',
    raised_at: '2026-08-18T12:00:00Z',
    age_days: 2.0,
    dismissed_at: null,
    dismissed_by_id: null,
    ...overrides,
  };
}

function renderCard(props: Partial<React.ComponentProps<typeof ParcelAlertsCard>> = {}) {
  return render(
    <MemoryRouter>
      <ParcelAlertsCard
        alerts={[buildAlert()]}
        syncedAt="2026-08-20T09:14:00Z"
        isLoading={false}
        dismissingId={null}
        onDismiss={vi.fn()}
        {...props}
      />
    </MemoryRouter>,
  );
}

describe('ParcelAlertsCard', () => {
  it('says all-clear quietly instead of rendering an empty loud box', () => {
    renderCard({ alerts: [] });

    expect(screen.getByText('Посилки: все гаразд')).toBeInTheDocument();
    // Naming the sync time is what separates "nothing is wrong" from "the
    // generator stopped running" on a surface nobody would otherwise check.
    expect(screen.getByText(/синхронізовано/)).toBeInTheDocument();
    expect(screen.queryByText('Посилки — потребують уваги')).not.toBeInTheDocument();
  });

  it('admits when the poll has never run rather than implying all is well', () => {
    renderCard({ alerts: [], syncedAt: null });

    expect(screen.getByText(/опитування ще не виконувалось/)).toBeInTheDocument();
  });

  it('shows the count and the alert rows when something needs attention', () => {
    renderCard({
      alerts: [
        buildAlert(),
        buildAlert({ id: 'alert-2', kind: 'no_data_stuck', detail: 'Без даних 9.7 дн.' }),
      ],
    });

    expect(screen.getByText('Посилки — потребують уваги')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getAllByTestId('parcel-alert-row')).toHaveLength(2);
    expect(screen.getByText('Прострочено 12.7 дн.')).toBeInTheDocument();
    expect(screen.getByText('Без даних 9.7 дн.')).toBeInTheDocument();
  });

  it('labels each kind with its own badge', () => {
    renderCard({
      alerts: [
        buildAlert({ id: 'a', kind: 'delivery_problem', detail: 'Проблема доставки — код 111' }),
        buildAlert({ id: 'b', kind: 'no_data_stuck' }),
        buildAlert({ id: 'c', kind: 'overdue_long' }),
        buildAlert({ id: 'd', kind: 'untracked_aging' }),
      ],
    });

    expect(screen.getByText('Проблема')).toBeInTheDocument();
    expect(screen.getByText('Без даних')).toBeInTheDocument();
    expect(screen.getByText('Прострочено')).toBeInTheDocument();
    expect(screen.getByText('Не відстежується')).toBeInTheDocument();
  });

  it('renders an unknown kind rather than crashing the dashboard', () => {
    renderCard({ alerts: [buildAlert({ kind: 'something_new', detail: 'Нове' })] });

    expect(screen.getByText('Потребує уваги')).toBeInTheDocument();
    expect(screen.getByText('Нове')).toBeInTheDocument();
  });

  it('collapses and expands from the header', () => {
    renderCard();

    const toggle = screen.getByRole('button', { name: /Посилки — потребують уваги/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('parcel-alert-row')).not.toBeInTheDocument();

    fireEvent.click(toggle);
    expect(screen.getAllByTestId('parcel-alert-row')).toHaveLength(1);
  });

  it('shows the carrier number on an untracked alert, which has no NP number', () => {
    // WB-TRACK-2 OQ1: an operator told to "check by hand" needs something to
    // check with. `tracking_number` is null for every untracked parcel.
    renderCard({
      alerts: [
        buildAlert({
          kind: 'untracked_aging',
          tracking_number: null,
          tracking_numbers: [
            { Identifier: 'WesternBid', TrackingNumber: 'WBX260000559260' },
            { Identifier: 'UPS', TrackingNumber: '1Z08W335D906259863' },
          ],
          detail: 'UPS — не відстежується, 21 дн.',
        }),
      ],
    });

    expect(screen.getByText(/1Z08W335D906259863/)).toBeInTheDocument();
  });

  it('keeps two alerts on the same parcel adjacent', () => {
    renderCard({
      alerts: [
        buildAlert({ id: 'a', kind: 'no_data_stuck', detail: 'Без даних 9.7 дн.' }),
        buildAlert({ id: 'b', kind: 'overdue_long', detail: 'Прострочено 14 дн.' }),
      ],
    });

    const rows = screen.getAllByTestId('parcel-alert-row');
    expect(within(rows[0]).getByText('Без даних 9.7 дн.')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Прострочено 14 дн.')).toBeInTheDocument();
  });

  it('reports which alert was dismissed', () => {
    const onDismiss = vi.fn();
    renderCard({ alerts: [buildAlert({ id: 'alert-42' })], onDismiss });

    fireEvent.click(screen.getByRole('button', { name: 'Опрацьовано' }));

    expect(onDismiss).toHaveBeenCalledWith('alert-42');
  });

  it('disables only the button whose dismiss is in flight', () => {
    renderCard({
      alerts: [buildAlert({ id: 'a' }), buildAlert({ id: 'b' })],
      dismissingId: 'a',
    });

    const [first, second] = screen.getAllByRole('button', { name: 'Опрацьовано' });
    expect(first).toBeDisabled();
    expect(second).toBeEnabled();
  });

  it('links out to the full parcel monitor', () => {
    renderCard();

    expect(screen.getByRole('link', { name: /Усі посилки/ })).toHaveAttribute(
      'href',
      '/westernbid',
    );
  });

  it('shows a skeleton while loading rather than a false all-clear', () => {
    renderCard({ isLoading: true, alerts: [] });

    expect(screen.queryByText('Посилки: все гаразд')).not.toBeInTheDocument();
  });
});
