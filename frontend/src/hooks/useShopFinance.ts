import { useQuery } from '@tanstack/react-query';

import { shopsApi } from '@/api/shops';
import type { ShopFinanceResponse } from '@/types/finance';

export function useShopFinance(
  shopId: string | undefined,
  startDate: string,
  endDate: string,
) {
  return useQuery<ShopFinanceResponse>({
    queryKey: ['shop-finance', shopId, startDate, endDate],
    queryFn: () => shopsApi.getShopFinance(shopId as string, startDate, endDate),
    enabled: Boolean(shopId && startDate && endDate),
  });
}
