import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import CustomersPage from '../CustomersPage';

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: {
      id: 'user-1',
      email: 'owner@orderhub.dev',
      full_name: 'Owner',
      role: 'owner',
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    isLoading: false,
    isAuthenticated: true,
    logout: vi.fn(),
    login: vi.fn(),
  }),
}));

vi.mock('@/hooks/useShops', () => ({
  useShops: () => ({ data: [], isLoading: false }),
}));

vi.mock('@/hooks/useCustomers', () => ({
  useCustomers: () => ({
    data: {
      items: [
        {
          id: 'cust-1',
          full_name: 'Jane Doe',
          email: 'jane@example.com',
          country: 'US',
          order_count: 3,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      limit: 20,
      pages: 1,
    },
    isLoading: false,
    isFetching: false,
    error: null,
  }),
}));

describe('CustomersPage smoke test', () => {
  it('renders customer list without crashing', () => {
    render(
      <MemoryRouter>
        <CustomersPage />
      </MemoryRouter>,
    );

    expect(screen.getByPlaceholderText('Search by customer name or email...')).toBeInTheDocument();
    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText('jane@example.com')).toBeInTheDocument();
  });
});
