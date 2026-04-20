import client from './client'
import type { ImportResult } from '@/types/common'

export const importsApi = {
  /**
   * Import orders from an Etsy CSV file.
   */
  importEtsyCsv: async (shopId: string, file: File): Promise<ImportResult> => {
    const formData = new FormData()
    formData.append('shop_id', shopId)
    formData.append('file', file)

    const { data } = await client.post<ImportResult>('/imports/etsy', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return data
  },
}
