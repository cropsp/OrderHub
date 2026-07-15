import { useQuery } from '@tanstack/react-query';
import client from '@/api/client';
import type { DashboardResponse } from '@/types/dashboard';

export const dashboardApi = {
  getStats: async (
    shopId?: string,
    startDate?: string,
    endDate?: string,
  ): Promise<DashboardResponse> => {
    const params: Record<string, string> = {};
    if (shopId) params.shop_id = shopId;
    // DASH-PERIOD: both dates or neither — the endpoint keeps its all-time
    // behaviour unless it gets a complete window.
    if (startDate && endDate) {
      params.start_date = startDate;
      params.end_date = endDate;
    }
    const { data } = await client.get('/dashboard', { params });
    return data;
  },
};

export function useDashboard(shopId?: string, startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: ['dashboard', shopId, startDate, endDate],
    queryFn: () => dashboardApi.getStats(shopId, startDate, endDate),
    refetchInterval: 60000, // Refresh every minute
  });
}
