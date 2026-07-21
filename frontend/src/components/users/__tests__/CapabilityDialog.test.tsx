import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import CapabilityDialog from '../CapabilityDialog';
import type { User } from '@/types/user';

const mutateAsync = vi.fn();
let capsData: { capabilities: Record<string, boolean> } = {
  capabilities: { view_finance: true, view_costs: false },
};

vi.mock('@/hooks/useUsers', () => ({
  useUserCapabilities: () => ({ data: capsData, isLoading: false }),
  useSetUserCapabilities: () => ({ mutateAsync, isPending: false }),
}));

const manager: User = {
  id: 'user-1',
  email: 'm@x.dev',
  full_name: 'Maya Manager',
  role: 'manager',
  is_active: true,
  preferences: {},
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const owner: User = { ...manager, id: 'user-2', full_name: 'Olga Owner', role: 'owner' };

beforeEach(() => {
  mutateAsync.mockReset();
  capsData = { capabilities: { view_finance: true, view_costs: false } };
});

describe('CapabilityDialog', () => {
  it('renders the capability checklist reflecting current grants', () => {
    render(<CapabilityDialog user={manager} open onOpenChange={() => {}} />);
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    expect(boxes).toHaveLength(2);
    expect(boxes[0].checked).toBe(true); // view_finance on
    expect(boxes[1].checked).toBe(false); // view_costs off
  });

  it('shows an unrestricted note for an owner target', () => {
    render(<CapabilityDialog user={owner} open onOpenChange={() => {}} />);
    expect(screen.getByText(/full financial visibility/i)).toBeInTheDocument();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('saves the toggled capabilities', async () => {
    mutateAsync.mockResolvedValue({
      capabilities: { view_finance: true, view_costs: true },
    });
    render(<CapabilityDialog user={manager} open onOpenChange={() => {}} />);
    fireEvent.click(screen.getAllByRole('checkbox')[1]); // enable view_costs
    fireEvent.click(screen.getByRole('button', { name: /save access/i }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledWith({
      id: 'user-1',
      capabilities: { view_finance: true, view_costs: true },
    });
  });
});
