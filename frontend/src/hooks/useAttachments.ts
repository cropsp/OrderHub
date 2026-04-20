import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { attachmentsApi } from '@/api/attachments'

export function useAttachments(orderId: string | null) {
  return useQuery({
    queryKey: ['attachments', orderId],
    queryFn: () => attachmentsApi.listByOrder(orderId as string),
    enabled: Boolean(orderId),
  })
}

export function useUploadAttachment() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ orderId, file, type }: { orderId: string; file: File; type?: string }) =>
      attachmentsApi.upload(orderId, file, type),
    onSuccess: (_, { orderId }) => {
      void queryClient.invalidateQueries({ queryKey: ['attachments', orderId] })
    },
  })
}

export function useDeleteAttachment() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (attachmentId: string) => attachmentsApi.delete(attachmentId),
    onSuccess: () => {
      // We don't have the orderId here, so we invalidate all attachments for safety
      // Or we could pass it in the mutationFn
      void queryClient.invalidateQueries({ queryKey: ['attachments'] })
    },
  })
}
