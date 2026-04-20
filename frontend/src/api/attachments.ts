import client from './client'
import type { AttachmentResponse } from '@/types/attachment'

export const attachmentsApi = {
  upload: async (orderId: string, file: File, type: string = 'other'): Promise<AttachmentResponse> => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('attachment_type', type)

    const { data } = await client.post<AttachmentResponse>(`/api/attachments/order/${orderId}`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return data
  },

  listByOrder: async (orderId: string): Promise<AttachmentResponse[]> => {
    const { data } = await client.get<AttachmentResponse[]>(`/api/attachments/order/${orderId}`)
    return data
  },

  delete: async (attachmentId: string): Promise<void> => {
    await client.delete(`/api/attachments/${attachmentId}`)
  },

  getDownloadUrl: (attachmentId: string): string => {
    return `${client.defaults.baseURL}/api/attachments/${attachmentId}`
  }
}
