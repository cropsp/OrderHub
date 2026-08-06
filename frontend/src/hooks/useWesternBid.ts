import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { westernBidApi } from '@/api/westernbid'
import { useToastStore } from '@/components/ui/Toast'
import { getApiErrorMessage } from '@/types/api'
import { NON_DELIVERED_STATES } from '@/types/westernbid'

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

/**
 * Everything the monitor shows above the fold — attention, untracked and in
 * transit — in one call (WB-TRACK-2). Delivered is fetched separately by
 * `useDeliveredParcels` so it can be paged; `counts` here still covers the full
 * set, which is what the collapsed group headers display.
 */
export function useTrackingOverview() {
  return useQuery({
    queryKey: ['westernbid', 'tracking', 'active'],
    queryFn: () => westernBidApi.getTracking({ states: NON_DELIVERED_STATES }),
  })
}

/**
 * The delivered group, paged. Lazy: nothing is fetched until the group is
 * expanded, because delivered parcels accumulate for the whole 60-day window
 * and are the one part of this page that grows without a natural bound.
 */
export function useDeliveredParcels(limit: number, offset: number, enabled: boolean) {
  return useQuery({
    queryKey: ['westernbid', 'tracking', 'delivered', { limit, offset }],
    queryFn: () =>
      westernBidApi.getTracking({ states: ['delivered'], limit, offset }),
    enabled,
  })
}

/** The transition log for one parcel. Fetched only once its row is expanded. */
export function useParcelEvents(trackingNumber: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['westernbid', 'tracking', 'events', trackingNumber],
    queryFn: () => westernBidApi.getTrackingEvents(trackingNumber as string),
    enabled: enabled && Boolean(trackingNumber),
  })
}

/**
 * Force a poll now rather than waiting for the daily job. The cooldown is
 * enforced by the server (429); disabling the button is only a courtesy.
 */
export function useRefreshTracking() {
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)

  return useMutation({
    mutationFn: () => westernBidApi.refreshTracking(),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['westernbid', 'tracking'] })
      addToast(
        result.changed > 0
          ? `Refreshed — ${result.changed} parcel(s) moved`
          : `Refreshed — nothing has moved since the last poll`,
        'success',
      )
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to refresh tracking'), 'error')
    },
  })
}
