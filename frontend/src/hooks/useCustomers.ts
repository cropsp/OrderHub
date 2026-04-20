import { useQuery } from '@tanstack/react-query';

import { customersApi } from '@/api/customers';
import type { CustomerListFilters } from '@/types/customer';

type UseCustomersOptions = {
  enabled?: boolean;
};

export function useCustomers(filters: CustomerListFilters = {}, options: UseCustomersOptions = {}) {
  const { enabled = true } = options;

  return useQuery({
    queryKey: ['customers', filters],
    queryFn: () => customersApi.list(filters),
    enabled,
  });
}

export function useCustomer(customerId: string | null, options: UseCustomersOptions = {}) {
  const { enabled = true } = options;

  return useQuery({
    queryKey: ['customers', customerId],
    queryFn: () => customersApi.getById(customerId as string),
    enabled: enabled && Boolean(customerId),
  });
}
