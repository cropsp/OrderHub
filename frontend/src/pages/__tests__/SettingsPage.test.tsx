import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import SettingsPage from '../SettingsPage';
import type { ApiKeyStatus } from '@/types/addressValidation';

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
vi.mock('@/hooks/useAppSettings', () => ({
  useAddressValidationKey: (...args: unknown[]) => mockAddressKeyQuery(...args),
  useSetAddressValidationKey: () => ({ mutateAsync: mockSetKey, isPending: false }),
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

function renderPage() {
  return render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUser.mockReturnValue(buildUser('owner'));
  mockAddressKeyQuery.mockReturnValue({ data: keyStatus(), isLoading: false });
  mockSetKey.mockResolvedValue(keyStatus({ is_set: true, last4: '1234' }));
});

describe('SettingsPage — Address Validation', () => {
  it('shows the not-configured state when no key is stored', () => {
    renderPage();

    expect(screen.getByText('Address Validation')).toBeInTheDocument();
    expect(screen.getByText('Not configured')).toBeInTheDocument();
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
