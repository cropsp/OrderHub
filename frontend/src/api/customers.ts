import client from './client';

import type { CustomerListFilters, CustomerListItem, CustomerListResponse } from '@/types/customer';

export const customersApi = {
  list: async (filters: CustomerListFilters = {}): Promise<CustomerListResponse> => {
    const { data } = await client.get<CustomerListResponse>('/customers', { params: filters });
    return data;
  },

  getById: async (customerId: string): Promise<CustomerListItem> => {
    const { data } = await client.get<CustomerListItem>(`/customers/${customerId}`);
    return data;
  },

  getByEmail: async (email: string): Promise<CustomerListItem> => {
    const { data } = await client.get<CustomerListItem>(`/customers/by-email/${email}`);
    return data;
  },
};
