/**
 * OrderHub CRM — WesternBid API client (WB-1)
 *
 * Read-only admin view of the WesternBid parcel mirror. OWNER + MANAGER.
 */

import client from '@/api/client'
import type { WbParcelListResponse } from '@/types/westernbid'

type WbParcelFilters = {
  page?: number
  limit?: number
}

export const westernBidApi = {
  listParcels: async (filters: WbParcelFilters = {}): Promise<WbParcelListResponse> => {
    const { data } = await client.get<WbParcelListResponse>('/westernbid/parcels', {
      params: filters,
    })
    return data
  },
}
