import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { partnersApi } from '@/api/partners'
import { useToastStore } from '@/components/ui/Toast'
import { getApiErrorMessage } from '@/types/api'
import type { ShopPartnerConfigUpsert } from '@/types/partner'

const PARTNERS_KEY = ['partners'] as const
const configKey = (shopId: string) => ['partner-config', shopId] as const

export function usePartners(includeInactive = false) {
  return useQuery({
    queryKey: [...PARTNERS_KEY, { includeInactive }],
    queryFn: () => partnersApi.list(includeInactive),
  })
}

export function useCreatePartner() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  return useMutation({
    mutationFn: (payload: { name: string; notes?: string | null }) =>
      partnersApi.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PARTNERS_KEY })
    },
    onError: (error) => {
      // A duplicate name is a 409, and its message names the existing partner —
      // surface it verbatim rather than a generic failure.
      addToast(getApiErrorMessage(error, 'Failed to create partner'), 'error')
    },
  })
}

export function useUpdatePartner() {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  return useMutation({
    mutationFn: ({
      partnerId,
      payload,
    }: {
      partnerId: string
      payload: { name?: string; is_active?: boolean; notes?: string | null }
    }) => partnersApi.update(partnerId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: PARTNERS_KEY })
      // A rename changes what every config row displays.
      queryClient.invalidateQueries({ queryKey: ['partner-config'] })
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to update partner'), 'error')
    },
  })
}

export function useShopPartnerConfigs(shopId: string | null) {
  return useQuery({
    queryKey: configKey(shopId ?? ''),
    queryFn: () => partnersApi.listShopConfigs(shopId as string),
    enabled: !!shopId,
  })
}

export function useUpsertShopPartnerConfig(shopId: string) {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  return useMutation({
    mutationFn: ({
      partnerId,
      payload,
    }: {
      partnerId: string
      payload: ShopPartnerConfigUpsert
    }) => partnersApi.upsertShopConfig(shopId, partnerId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: configKey(shopId) })
      addToast('Partner configuration saved', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to save configuration'), 'error')
    },
  })
}

export function useDeleteShopPartnerConfig(shopId: string) {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  return useMutation({
    mutationFn: (partnerId: string) =>
      partnersApi.deleteShopConfig(shopId, partnerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: configKey(shopId) })
      // Settlements and payments are untouched — the money is still owed.
      addToast('Partner removed from this shop', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to remove partner'), 'error')
    },
  })
}
