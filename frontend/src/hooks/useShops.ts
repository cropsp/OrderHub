import { useQuery } from '@tanstack/react-query'

import { shopsApi } from '@/api/shops'

type UseShopsOptions = {
  enabled?: boolean
}

export function useShops(options: UseShopsOptions = {}) {
  const { enabled = true } = options

  return useQuery({
    queryKey: ['shops'],
    queryFn: shopsApi.list,
    enabled,
  })
}
