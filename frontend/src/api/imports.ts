import client from './client'
import type { ImportResult, StatementImportReport } from '@/types/common'

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

  /**
   * Import one monthly Etsy payment-account statement (STATEMENT-IMPORT).
   * Idempotent per calendar month: re-uploading replaces that period's lines
   * and recomputes the affected fees, so running it twice is a no-op.
   */
  importEtsyStatement: async (
    shopId: string,
    file: File,
  ): Promise<StatementImportReport> => {
    const formData = new FormData()
    formData.append('shop_id', shopId)
    formData.append('file', file)

    const { data } = await client.post<StatementImportReport>(
      '/imports/etsy-statement',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      },
    )
    return data
  },
}
