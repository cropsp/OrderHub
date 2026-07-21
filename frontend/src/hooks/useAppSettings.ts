import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { appSettingsApi } from '@/api/appSettings'
import type { WesternBidCredentialsUpdate } from '@/types/westernbid'

const ADDRESS_VALIDATION_KEY = ['app-settings', 'address-validation']
const WESTERNBID_CREDENTIALS_KEY = ['app-settings', 'westernbid']

type UseAddressValidationKeyOptions = {
  enabled?: boolean
}

/** Masked status of the Google Address Validation key. Owner-only endpoint —
 *  pass `enabled: false` for non-owners so it doesn't fire and 403. */
export function useAddressValidationKey(options: UseAddressValidationKeyOptions = {}) {
  const { enabled = true } = options

  return useQuery({
    queryKey: ADDRESS_VALIDATION_KEY,
    queryFn: appSettingsApi.getAddressValidationKey,
    enabled,
  })
}

export function useSetAddressValidationKey() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (apiKey: string) => appSettingsApi.setAddressValidationKey(apiKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ADDRESS_VALIDATION_KEY })
    },
  })
}

type UseWesternBidCredentialsOptions = {
  enabled?: boolean
}

/** Masked status of the WesternBid credential pair. Owner-only endpoint —
 *  pass `enabled: false` for non-owners so it doesn't fire and 403. */
export function useWesternBidCredentials(options: UseWesternBidCredentialsOptions = {}) {
  const { enabled = true } = options

  return useQuery({
    queryKey: WESTERNBID_CREDENTIALS_KEY,
    queryFn: appSettingsApi.getWesternBidCredentials,
    enabled,
  })
}

export function useSetWesternBidCredentials() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: WesternBidCredentialsUpdate) =>
      appSettingsApi.setWesternBidCredentials(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: WESTERNBID_CREDENTIALS_KEY })
    },
  })
}
