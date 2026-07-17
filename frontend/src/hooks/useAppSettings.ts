import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { appSettingsApi } from '@/api/appSettings'

const ADDRESS_VALIDATION_KEY = ['app-settings', 'address-validation']

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
