import { useQuery } from '@tanstack/react-query';
import client from '@/api/client';
import type { DashboardResponse } from '@/types/dashboard';

export const dashboardApi = {
  getStats: async (shopId?: string): Promise<DashboardResponse> => {
    const params = shopId ? { shop_id: shopId } : {};
    const { data } = await client.get('/dashboard', { params });
    return data;
  },
};

export function useDashboard(shopId?: string) {
  return useQuery({
    queryKey: ['dashboard', shopId],
    queryFn: () => dashboardApi.getStats(shopId),
    refetchInterval: 60000, // Refresh every minute
  });
}
