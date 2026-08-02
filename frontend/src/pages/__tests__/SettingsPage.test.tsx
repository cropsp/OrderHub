import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import SettingsPage from '../SettingsPage';
import type { ApiKeyStatus } from '@/types/addressValidation';
import type { FxSettings } from '@/types/fx';

const mockUser = vi.fn();
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: mockUser(),
    isLoading: false,
    isAuthenticated: true,
    logout: vi.fn(),
    login: vi.fn(),
  }),
}));

vi.mock('@/hooks/useUsers', () => ({
  useUpdatePreferences: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

// ShellPage (the surrounding shell) pulls in useShops, which needs a QueryClient.
vi.mock('@/hooks/useShops', () => ({
  useShops: () => ({ data: [], isLoading: false }),
}));

const mockAddressKeyQuery = vi.fn();
const mockSetKey = vi.fn();
const mockWbQuery = vi.fn();
const mockFxQuery = vi.fn();
const mockSetFx = vi.fn();
const mockClearFxOverride = vi.fn();
// Every hook the page calls must appear here — vi.mock replaces the module
// wholesale, so a missing export throws at render rather than falling through.
vi.mock('@/hooks/useAppSettings', () => ({
  useAddressValidationKey: (...args: unknown[]) => mockAddressKeyQuery(...args),
  useSetAddressValidationKey: () => ({ mutateAsync: mockSetKey, isPending: false }),
  useWesternBidCredentials: (...args: unknown[]) => mockWbQuery(...args),
  useSetWesternBidCredentials: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useFxSettings: (...args: unknown[]) => mockFxQuery(...args),
  useSetFxSettings: () => ({ mutateAsync: mockSetFx, isPending: false }),
  useClearFxOverride: () => ({ mutateAsync: mockClearFxOverride, isPending: false }),
}));

function buildUser(role: string) {
  return {
    id: 'user-1',
    email: 'someone@orderhub.dev',
    full_name: 'Someone',
    role,
    is_active: true,
    preferences: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

function keyStatus(overrides: Partial<ApiKeyStatus> = {}): ApiKeyStatus {
  return { is_set: false, last4: null, updated_at: null, ...overrides };
}

function fxSettings(overrides: Partial<FxSettings> = {}): FxSettings {
  return {
    uah_per_usd_effective: null,
    source: null,
    uah_per_usd_override: null,
    uah_per_usd_cached: null,
    rate_date: null,
    fetched_at: null,
    is_stale: false,
    source_url: 'https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&json',
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );
}

/** Scope a query to one settings card. Several cards render the same badge text
 *  ("Not configured"), so page-wide getByText is ambiguous. */
function card(title: string): HTMLElement {
  const heading = screen.getByText(title);
  const root = heading.closest('[class*="backdrop-blur-sm"]');
  if (!root) throw new Error(`Could not find the card containing "${title}"`);
  return root as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUser.mockReturnValue(buildUser('owner'));
  mockAddressKeyQuery.mockReturnValue({ data: keyStatus(), isLoading: false });
  mockSetKey.mockResolvedValue(keyStatus({ is_set: true, last4: '1234' }));
  mockWbQuery.mockReturnValue({ data: undefined, isLoading: false });
  mockFxQuery.mockReturnValue({ data: fxSettings(), isLoading: false });
  mockSetFx.mockResolvedValue(fxSettings());
  mockClearFxOverride.mockResolvedValue(fxSettings());
});

describe('SettingsPage — Address Validation', () => {
  it('shows the not-configured state when no key is stored', () => {
    renderPage();

    expect(screen.getByText('Address Validation')).toBeInTheDocument();
    expect(within(card('Address Validation')).getByText('Not configured')).toBeInTheDocument();
  });

  it('shows the masked last4 when a key is stored', () => {
    mockAddressKeyQuery.mockReturnValue({
      data: keyStatus({ is_set: true, last4: '1234' }),
      isLoading: false,
    });

    renderPage();

    expect(screen.getByText('Configured ••••1234')).toBeInTheDocument();
  });

  it('never pre-fills the key input, and masks it', () => {
    mockAddressKeyQuery.mockReturnValue({
      data: keyStatus({ is_set: true, last4: '1234' }),
      isLoading: false,
    });

    renderPage();
    const input = screen.getByPlaceholderText('Leave empty to keep existing');

    expect(input).toHaveValue('');
    expect(input).toHaveAttribute('type', 'password');
  });

  it('saves a trimmed key and clears the input', async () => {
    renderPage();
    const input = screen.getByPlaceholderText('Google API key');

    fireEvent.change(input, { target: { value: '  AIzaSyExample1234  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Key' }));

    await waitFor(() => expect(mockSetKey).toHaveBeenCalledWith('AIzaSyExample1234'));
    await waitFor(() => expect(input).toHaveValue(''));
    expect(await screen.findByText('API key saved.')).toBeInTheDocument();
  });

  it('disables save while the input is empty', () => {
    renderPage();

    expect(screen.getByRole('button', { name: 'Save Key' })).toBeDisabled();
  });

  it('surfaces a failure without clearing the input', async () => {
    mockSetKey.mockRejectedValue(new Error('403'));
    renderPage();
    const input = screen.getByPlaceholderText('Google API key');

    fireEvent.change(input, { target: { value: 'bad-key' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Key' }));

    expect(await screen.findByText('Failed to save the API key.')).toBeInTheDocument();
    expect(input).toHaveValue('bad-key');
  });

  it.each(['manager', 'designer'])(
    'hides the card and skips the owner-only query for %s',
    (role) => {
      mockUser.mockReturnValue(buildUser(role));

      renderPage();

      expect(screen.queryByText('Address Validation')).not.toBeInTheDocument();
      // The endpoint is owner-only — a non-owner must not fire it and 403.
      expect(mockAddressKeyQuery).toHaveBeenCalledWith({ enabled: false });
    },
  );

  it('enables the query for an owner', () => {
    renderPage();

    expect(mockAddressKeyQuery).toHaveBeenCalledWith({ enabled: true });
  });
});

describe('SettingsPage — Exchange Rate (FX-CONVERSION)', () => {
  it('shows the effective NBU rate and its source', () => {
    mockFxQuery.mockReturnValue({
      data: fxSettings({
        uah_per_usd_effective: '44.6395',
        uah_per_usd_cached: '44.6395',
        source: 'nbu',
        rate_date: '2026-08-03',
      }),
      isLoading: false,
    });

    renderPage();

    expect(screen.getByText('44.6395 UAH per $1 · NBU')).toBeInTheDocument();
    expect(screen.getByText('NBU date 2026-08-03')).toBeInTheDocument();
  });

  it('warns when no rate is configured at all', () => {
    renderPage();

    expect(screen.getByText('No rate yet')).toBeInTheDocument();
  });

  it('flags a stale auto rate', () => {
    mockFxQuery.mockReturnValue({
      data: fxSettings({ uah_per_usd_effective: '44.6395', source: 'nbu', is_stale: true }),
      isLoading: false,
    });

    renderPage();

    expect(screen.getByText('Stale')).toBeInTheDocument();
  });

  it('says what clearing the override would revert to, before it is clicked', () => {
    // Clearing silently changes the rate every future shipment books at, so the
    // destination has to be visible up front.
    mockFxQuery.mockReturnValue({
      data: fxSettings({
        uah_per_usd_effective: '41.5',
        uah_per_usd_override: '41.5',
        uah_per_usd_cached: '44.6395',
        source: 'manual',
      }),
      isLoading: false,
    });

    renderPage();

    expect(
      screen.getByText(/Clearing reverts to 44.6395 UAH per \$1 \(NBU\)/),
    ).toBeInTheDocument();
  });

  it('warns when clearing would leave no rate at all', () => {
    mockFxQuery.mockReturnValue({
      data: fxSettings({
        uah_per_usd_effective: '41.5',
        uah_per_usd_override: '41.5',
        uah_per_usd_cached: null,
        source: 'manual',
      }),
      isLoading: false,
    });

    renderPage();

    expect(screen.getByText(/no rate at all — nothing would convert/)).toBeInTheDocument();
  });

  it('sends a trimmed override and clears the input', async () => {
    renderPage();
    const input = screen.getByPlaceholderText('e.g. 41.5 (UAH per $1)');

    fireEvent.change(input, { target: { value: '  41.5  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Set' }));

    await waitFor(() =>
      expect(mockSetFx).toHaveBeenCalledWith({ uah_per_usd_override: '41.5' }),
    );
    await waitFor(() => expect(input).toHaveValue(''));
  });

  it('reverts to auto through the dedicated clear endpoint', async () => {
    mockFxQuery.mockReturnValue({
      data: fxSettings({
        uah_per_usd_effective: '41.5',
        uah_per_usd_override: '41.5',
        uah_per_usd_cached: '44.6395',
        source: 'manual',
      }),
      isLoading: false,
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Revert to auto' }));

    await waitFor(() => expect(mockClearFxOverride).toHaveBeenCalled());
  });

  it.each(['manager', 'designer'])(
    'hides the card and skips the owner-only query for %s',
    (role) => {
      mockUser.mockReturnValue(buildUser(role));

      renderPage();

      expect(screen.queryByText('Exchange Rate (UAH → USD)')).toBeNull();
      expect(mockFxQuery).toHaveBeenCalledWith({ enabled: false });
    },
  );
});
