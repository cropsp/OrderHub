import { useQuery } from '@tanstack/react-query'

import { westernBidApi } from '@/api/westernbid'

type UseWbParcelsOptions = {
  page?: number
  limit?: number
  enabled?: boolean
}

/** Read-only WesternBid parcel mirror, newest first (WB-1). OWNER + MANAGER. */
export function useWbParcels(options: UseWbParcelsOptions = {}) {
  const { page = 1, limit = 50, enabled = true } = options

  return useQuery({
    queryKey: ['westernbid', 'parcels', { page, limit }],
    queryFn: () => westernBidApi.listParcels({ page, limit }),
    enabled,
  })
}
