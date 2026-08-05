import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AddressValidation } from '../AddressValidation';
import { AddressBadge } from '@/components/ui/AddressBadge';
import { useValidateAddress } from '@/hooks/useOrders';
import { useAuth } from '@/hooks/useAuth';
import { UserRole } from '@/types/user';
import type { OrderDetail } from '@/types/order';
import type { AddressValidationStatus, AddressVerdict } from '@/types/addressValidation';

vi.mock('@/hooks/useOrders', () => ({ useValidateAddress: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: vi.fn() }));

function makeOrder(overrides: Partial<OrderDetail> = {}): OrderDetail {
  return {
    id: 'order-1', external_id: 'EXT-1', shop_id: 'shop-1', customer_id: 'cust-1',
    status: 'new' as OrderDetail['status'], title: 'T', total_price: 100, currency: 'USD',
    production_cost: null, computed_production_cost: null, shipping_np_cost: null, platform_fee: null,
    shipping_revenue: null, discount_total: null, tax_total: null,
    shipping_name: 'Jane', shipping_phone: null, shipping_street_1: '10 Education Cir', shipping_street_2: null,
    shipping_city: 'Cambridge', shipping_state: 'MA', shipping_zip: '02141', shipping_country: 'US',
    shipping_city_ref: null, shipping_warehouse_ref: null, assigned_designer_id: null, assigned_at: null,
    ttn_number: null, ttn_created_at: null, ttn_printed: false, customer_note: null, custom_info: null,
    internal_note: null, ordered_at: '2026-07-17T10:00:00Z', shipped_at: null, completed_at: null,
    created_at: '2026-07-17T10:00:00Z', updated_at: '2026-07-17T10:00:00Z', parcel_override: false,
    shop_name: 'Shop', customer_name: 'Jane', platform: 'manual', items: [], status_history: [],
    ...overrides,
  };
}

function verdict(overrides: Partial<AddressVerdict> = {}): AddressVerdict {
  return {
    status: 'needs_attention', message: null, formatted_address: null,
    components: null, diff: [], validated_at: '2026-07-17T12:00:00Z', ...overrides,
  };
}

let mutateAsync: ReturnType<typeof vi.fn>;

function setValidate(isPending = false) {
  mutateAsync = vi.fn();
  vi.mocked(useValidateAddress).mockReturnValue({ mutateAsync, isPending } as never);
}

function setRole(role: string) {
  vi.mocked(useAuth).mockReturnValue({ user: { role } } as never);
}

function renderAV(props: Partial<React.ComponentProps<typeof AddressValidation>> = {}) {
  return render(
    <MemoryRouter>
      <AddressValidation order={makeOrder()} canManageShipping onApply={vi.fn()} {...props} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  setValidate();
  setRole(UserRole.OWNER);
});
afterEach(() => vi.clearAllMocks());

describe('AddressBadge (OQ-2 mapping)', () => {
  it.each<[AddressValidationStatus, string]>([
    ['verified', 'Verified'],
    ['needs_attention', 'Needs attention'],
    ['couldnt_verify', "Couldn't verify"],
    ['unsupported', 'Not supported here'],
    ['unavailable', 'Validation unavailable'],
  ])('renders %s as "%s"', (status, label) => {
    render(<AddressBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('renders nothing for ua', () => {
    const { container } = render(<AddressBadge status="ua" />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('AddressValidation', () => {
  it('renders the persisted status badge on load (OQ-5)', () => {
    renderAV({ order: makeOrder({ address_validation_status: 'needs_attention', address_validation_at: '2026-07-17T12:00:00Z' }) });
    expect(screen.getByText('Needs attention')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /re-check/i })).toBeInTheDocument();
  });

  it('renders nothing for a UA order', () => {
    const { container } = renderAV({ order: makeOrder({ shipping_country: 'UA' }) });
    expect(container).toBeEmptyDOMElement();
  });

  it('disables the button with a hint when the order has no address', () => {
    renderAV({ order: makeOrder({ shipping_street_1: null, shipping_city: null, shipping_zip: null }) });
    expect(screen.getByRole('button', { name: /check address/i })).toBeDisabled();
    expect(screen.getByText(/add a street address/i)).toBeInTheDocument();
  });

  it('disables the button when the order has city/country but no street (matches "No address provided")', () => {
    renderAV({ order: makeOrder({ shipping_street_1: null, shipping_city: 'Cambridge', shipping_zip: null, shipping_country: 'US' }) });
    expect(screen.getByRole('button', { name: /check address/i })).toBeDisabled();
    expect(screen.getByText(/add a street address/i)).toBeInTheDocument();
  });

  it('shows an actionable diff + Apply after a check with a real change', async () => {
    mutateAsync = vi.fn().mockResolvedValue(verdict({
      status: 'needs_attention',
      diff: [{ field: 'city', original: 'Redbridge, London', suggested: 'London' }],
    }));
    vi.mocked(useValidateAddress).mockReturnValue({ mutateAsync, isPending: false } as never);

    renderAV();
    fireEvent.click(screen.getByRole('button', { name: /check address/i }));

    expect(await screen.findByText('Suggested changes')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /apply suggestion/i })).toBeInTheDocument();
    expect(mutateAsync).toHaveBeenCalledWith('order-1');
  });

  it('de-emphasises a cosmetic-only diff (no nagging Apply-suggestion box)', async () => {
    mutateAsync = vi.fn().mockResolvedValue(verdict({
      status: 'verified',
      diff: [{ field: 'zip', original: '02141', suggested: '02141-1970' }],
    }));
    vi.mocked(useValidateAddress).mockReturnValue({ mutateAsync, isPending: false } as never);

    renderAV();
    fireEvent.click(screen.getByRole('button', { name: /check address/i }));

    expect(await screen.findByText(/minor formatting differences/i)).toBeInTheDocument();
    expect(screen.queryByText('Suggested changes')).toBeNull();
  });

  it('Apply writes only shipping_* fields (never country) through the update path', async () => {
    mutateAsync = vi.fn().mockResolvedValue(verdict({
      status: 'needs_attention',
      diff: [
        { field: 'city', original: 'Redbridge, London', suggested: 'London' },
        { field: 'country', original: 'GB', suggested: 'GB' },
      ],
    }));
    vi.mocked(useValidateAddress).mockReturnValue({ mutateAsync, isPending: false } as never);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const onApply = vi.fn().mockResolvedValue(undefined);

    renderAV({ onApply });
    fireEvent.click(screen.getByRole('button', { name: /check address/i }));
    fireEvent.click(await screen.findByRole('button', { name: /apply suggestion/i }));

    await waitFor(() => expect(onApply).toHaveBeenCalledTimes(1));
    const payload = onApply.mock.calls[0][0];
    expect(payload).toEqual({ shipping_city: 'London' });
    expect(payload).not.toHaveProperty('shipping_country');
  });

  it('shows an owner-only Settings hint when unavailable (OQ-6)', () => {
    renderAV({ order: makeOrder({ address_validation_status: 'unavailable' }) });
    expect(screen.getByText(/set one in settings/i)).toBeInTheDocument();
  });

  it('hides the Settings hint from non-owners', () => {
    setRole(UserRole.MANAGER);
    renderAV({ order: makeOrder({ address_validation_status: 'unavailable' }), canManageShipping: true });
    expect(screen.queryByText(/set one in settings/i)).toBeNull();
  });

  it('hides the check button from users who cannot manage shipping', () => {
    renderAV({ canManageShipping: false });
    expect(screen.queryByRole('button', { name: /check address/i })).toBeNull();
  });
});
