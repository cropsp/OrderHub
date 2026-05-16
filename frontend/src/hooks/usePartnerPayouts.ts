import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  partnerPayoutsApi,
  type PaymentCreateRequest,
  type PreviewRequest,
  type SettlementCreateRequest,
} from '@/api/partnerPayouts'
import { useToastStore } from '@/components/ui/Toast'
import { getApiErrorMessage } from '@/types/api'

const baseKey = (shopId: string) => ['partner-payouts', shopId] as const

function invalidateAfterSettlement(
  queryClient: ReturnType<typeof useQueryClient>,
  shopId: string,
) {
  queryClient.invalidateQueries({ queryKey: [...baseKey(shopId), 'settlements'] })
  queryClient.invalidateQueries({ queryKey: [...baseKey(shopId), 'balances'] })
  queryClient.invalidateQueries({ queryKey: [...baseKey(shopId), 'partner-names'] })
}

function invalidateAfterPayment(
  queryClient: ReturnType<typeof useQueryClient>,
  shopId: string,
) {
  queryClient.invalidateQueries({ queryKey: [...baseKey(shopId), 'payments'] })
  queryClient.invalidateQueries({ queryKey: [...baseKey(shopId), 'balances'] })
  queryClient.invalidateQueries({ queryKey: [...baseKey(shopId), 'partner-names'] })
  // Settlements list shows paid_amount badges — refresh those too.
  queryClient.invalidateQueries({ queryKey: [...baseKey(shopId), 'settlements'] })
}

export function useSettlements(
  shopId: string,
  params: { partner?: string; limit?: number; offset?: number } = {},
) {
  return useQuery({
    queryKey: [...baseKey(shopId), 'settlements', params],
    queryFn: () => partnerPayoutsApi.listSettlements(shopId, params),
    enabled: !!shopId,
  })
}

export function usePayments(
  shopId: string,
  params: {
    partner?: string
    settlement_id?: string
    limit?: number
    offset?: number
  } = {},
) {
  return useQuery({
    queryKey: [...baseKey(shopId), 'payments', params],
    queryFn: () => partnerPayoutsApi.listPayments(shopId, params),
    enabled: !!shopId,
  })
}

export function usePartnerBalances(shopId: string) {
  return useQuery({
    queryKey: [...baseKey(shopId), 'balances'],
    queryFn: () => partnerPayoutsApi.getBalances(shopId),
    enabled: !!shopId,
  })
}

export function usePartnerNames(shopId: string) {
  return useQuery({
    queryKey: [...baseKey(shopId), 'partner-names'],
    queryFn: () => partnerPayoutsApi.getPartnerNames(shopId),
    enabled: !!shopId,
  })
}

export function usePreviewSettlement(shopId: string) {
  return useMutation({
    mutationFn: (payload: PreviewRequest) =>
      partnerPayoutsApi.preview(shopId, payload),
  })
}

export function useCreateSettlement(shopId: string) {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  return useMutation({
    mutationFn: (payload: SettlementCreateRequest) =>
      partnerPayoutsApi.createSettlement(shopId, payload),
    onSuccess: () => {
      invalidateAfterSettlement(queryClient, shopId)
      addToast('Settlement saved', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to save settlement'), 'error')
    },
  })
}

export function useDeleteSettlement(shopId: string) {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  return useMutation({
    mutationFn: (settlementId: string) =>
      partnerPayoutsApi.deleteSettlement(shopId, settlementId),
    onSuccess: () => {
      invalidateAfterSettlement(queryClient, shopId)
      // Linked payments survive with settlement_id=NULL — refresh ledger.
      queryClient.invalidateQueries({ queryKey: [...baseKey(shopId), 'payments'] })
      addToast('Settlement deleted', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to delete settlement'), 'error')
    },
  })
}

export function useCreatePayment(shopId: string) {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  return useMutation({
    mutationFn: (payload: PaymentCreateRequest) =>
      partnerPayoutsApi.createPayment(shopId, payload),
    onSuccess: () => {
      invalidateAfterPayment(queryClient, shopId)
      addToast('Payment recorded', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to record payment'), 'error')
    },
  })
}

export function useDeletePayment(shopId: string) {
  const queryClient = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  return useMutation({
    mutationFn: (paymentId: string) =>
      partnerPayoutsApi.deletePayment(shopId, paymentId),
    onSuccess: () => {
      invalidateAfterPayment(queryClient, shopId)
      addToast('Payment deleted', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Failed to delete payment'), 'error')
    },
  })
}
