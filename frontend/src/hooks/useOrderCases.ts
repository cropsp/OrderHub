import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { orderCasesApi } from '@/api/orderCases'
import { useToastStore } from '@/components/ui/Toast'
import { getApiErrorMessage } from '@/types/api'
import type {
  OrderCaseCreatePayload,
  OrderCaseUpdatePayload,
} from '@/types/orderCase'

/**
 * Cases of one order (CASE-1).
 *
 * Fetched by the order-card section itself rather than folded into
 * `OrderResponse` — the precedent is `AttachmentManager`, which takes an
 * orderId and owns its own query. Two reasons it matters here: the orders LIST
 * would otherwise pay for cases nothing on it renders, and `OrderResponse`
 * stays untouched, which keeps this feature off the money-classification
 * surface entirely.
 */
export function useOrderCases(orderId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ['order-cases', orderId],
    queryFn: () => orderCasesApi.listForOrder(orderId as string),
    enabled: Boolean(orderId) && enabled,
  })
}

/**
 * Open cases for the dashboard block.
 *
 * `enabled` gates the fetch rather than the call, because hooks cannot be
 * called conditionally: the dashboard renders for DESIGNERs too, and
 * `/cases/open` is OWNER+MANAGER-gated server-side.
 *
 * Deliberately NOT scoped by the dashboard period selector — like the parcel
 * alerts beside it, this is an attention queue and stays live.
 */
export function useOpenCases(enabled: boolean) {
  return useQuery({
    queryKey: ['order-cases', 'open'],
    queryFn: () => orderCasesApi.listOpen(),
    enabled,
  })
}

/** Both surfaces can change what the other shows, so both are invalidated. */
function useCaseInvalidation() {
  const queryClient = useQueryClient()
  return (orderId?: string) => {
    queryClient.invalidateQueries({ queryKey: ['order-cases', 'open'] })
    if (orderId) {
      queryClient.invalidateQueries({ queryKey: ['order-cases', orderId] })
    }
  }
}

export function useCreateCase(orderId: string) {
  const invalidate = useCaseInvalidation()
  const addToast = useToastStore((s) => s.addToast)

  return useMutation({
    mutationFn: (payload: OrderCaseCreatePayload) =>
      orderCasesApi.create(orderId, payload),
    onSuccess: () => {
      invalidate(orderId)
      addToast('Питання створено', 'success')
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Не вдалося створити питання'), 'error')
    },
  })
}

export function useUpdateCase(orderId: string) {
  const invalidate = useCaseInvalidation()
  const addToast = useToastStore((s) => s.addToast)

  return useMutation({
    mutationFn: ({
      caseId,
      payload,
    }: {
      caseId: string
      payload: OrderCaseUpdatePayload
    }) => orderCasesApi.update(caseId, payload),
    onSuccess: () => {
      invalidate(orderId)
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Не вдалося оновити питання'), 'error')
    },
  })
}

export function useAddCaseNote(orderId: string) {
  const invalidate = useCaseInvalidation()
  const addToast = useToastStore((s) => s.addToast)

  return useMutation({
    mutationFn: ({ caseId, text }: { caseId: string; text: string }) =>
      orderCasesApi.addNote(caseId, text),
    onSuccess: () => {
      invalidate(orderId)
    },
    onError: (error) => {
      addToast(getApiErrorMessage(error, 'Не вдалося додати нотатку'), 'error')
    },
  })
}
