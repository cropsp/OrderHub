/**
 * OrderHub CRM — WesternBid API client (WB-1)
 *
 * Read-only admin view of the WesternBid parcel mirror. OWNER + MANAGER.
 */

import client from '@/api/client'
import type {
  ParcelState,
  TrackingEvent,
  TrackingOverview,
  TrackingRefreshResult,
  WbParcelListResponse,
} from '@/types/westernbid'

type WbParcelFilters = {
  page?: number
  limit?: number
}

type TrackingFilters = {
  /** One state or a set of them; the server accepts a comma-separated list. */
  states?: readonly ParcelState[]
  limit?: number
  offset?: number
}

export const westernBidApi = {
  listParcels: async (filters: WbParcelFilters = {}): Promise<WbParcelListResponse> => {
    const { data } = await client.get<WbParcelListResponse>('/westernbid/parcels', {
      params: filters,
    })
    return data
  },

  /** Delivery status of every parcel in the tracking window (WB-TRACK-1). */
  getTracking: async (filters: TrackingFilters = {}): Promise<TrackingOverview> => {
    const { states, limit, offset } = filters
    const { data } = await client.get<TrackingOverview>('/westernbid/tracking', {
      params: {
        state: states?.length ? states.join(',') : undefined,
        limit,
        offset,
      },
    })
    return data
  },

  /** The transition log for one parcel, oldest first (WB-TRACK-2). */
  getTrackingEvents: async (trackingNumber: string): Promise<TrackingEvent[]> => {
    const { data } = await client.get<TrackingEvent[]>(
      `/westernbid/tracking/${encodeURIComponent(trackingNumber)}/events`,
    )
    return data
  },

  /** Force a poll now. Throttled server-side — a 429 here is expected. */
  refreshTracking: async (): Promise<TrackingRefreshResult> => {
    const { data } = await client.post<TrackingRefreshResult>(
      '/westernbid/tracking/refresh',
    )
    return data
  },
}
