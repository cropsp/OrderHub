import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import ShopAccessDialog from '../ShopAccessDialog';
import type { User } from '@/types/user';

const shops = [
  { id: 'shop-a', name: 'Leather Co', platform: 'manual', color: '#fff', is_active: true },
  { id: 'shop-b', name: 'Etsy Store', platform: 'etsy', color: '#fff', is_active: true },
];

const mutateAsync = vi.fn();
let accessData: { shop_ids: string[] } = { shop_ids: ['shop-a'] };

vi.mock('@/hooks/useShops', () => ({
  useShops: () => ({ data: shops, isLoading: false }),
}));

vi.mock('@/hooks/useUsers', () => ({
  useUserShopAccess: () => ({ data: accessData, isLoading: false }),
  useSetUserShopAccess: () => ({ mutateAsync, isPending: false }),
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
  accessData = { shop_ids: ['shop-a'] };
});

describe('ShopAccessDialog', () => {
  it('renders the shop checklist with the current grants checked', () => {
    render(<ShopAccessDialog user={manager} open onOpenChange={() => {}} />);
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    expect(boxes).toHaveLength(2);
    expect(boxes[0].checked).toBe(true); // shop-a granted
    expect(boxes[1].checked).toBe(false); // shop-b not
  });

  it('shows an unrestricted note for an owner target', () => {
    render(<ShopAccessDialog user={owner} open onOpenChange={() => {}} />);
    expect(screen.getByText(/unrestricted access to every shop/i)).toBeInTheDocument();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('saves the selected shop ids', async () => {
    mutateAsync.mockResolvedValue({ shop_ids: ['shop-a', 'shop-b'] });
    render(<ShopAccessDialog user={manager} open onOpenChange={() => {}} />);
    fireEvent.click(screen.getAllByRole('checkbox')[1]); // add shop-b
    fireEvent.click(screen.getByRole('button', { name: /save access/i }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(mutateAsync).toHaveBeenCalledWith({
      id: 'user-1',
      shop_ids: ['shop-a', 'shop-b'],
      unassign_orders: false,
    });
  });

  it('surfaces the 409 confirm and re-submits with unassign_orders', async () => {
    mutateAsync
      .mockRejectedValueOnce({
        response: { status: 409, data: { detail: { blocked: [{ shop_id: 'shop-a', assigned_order_count: 3 }] } } },
      })
      .mockResolvedValueOnce({ shop_ids: [] });
    render(<ShopAccessDialog user={manager} open onOpenChange={() => {}} />);
    fireEvent.click(screen.getAllByRole('checkbox')[0]); // remove shop-a
    fireEvent.click(screen.getByRole('button', { name: /save access/i }));

    await waitFor(() => expect(screen.getByText(/assigned order/i)).toBeInTheDocument());
    expect(screen.getByText(/3/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /unassign & revoke/i }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2));
    expect(mutateAsync.mock.calls[1][0]).toMatchObject({ unassign_orders: true });
  });
});
