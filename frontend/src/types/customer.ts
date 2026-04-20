import type { PaginatedResponse } from './common';

export interface CustomerListItem {
  id: string;
  email: string;
  full_name: string;
  country: string | null;
  created_at: string;
  updated_at: string;
  order_count: number;
}

export interface CustomerListFilters {
  page?: number;
  limit?: number;
  search?: string;
}

export type CustomerListResponse = PaginatedResponse<CustomerListItem>;
