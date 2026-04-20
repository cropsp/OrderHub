import { useQuery } from '@tanstack/react-query';
import client from '@/api/client';
import type { DashboardResponse } from '@/types/dashboard';

export const dashboardApi = {
  getStats: async (): Promise<DashboardResponse> => {
    const { data } = await client.get('/dashboard');
    return data;
  },
};

export function useDashboard() {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: dashboardApi.getStats,
    refetchInterval: 60000, // Refresh every minute
  });
}
