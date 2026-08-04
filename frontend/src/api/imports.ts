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
   *
   * `dryRun` must be sent explicitly — the backend defaults it to TRUE, so an
   * omitted flag rehearses rather than books.
   */
  importEtsyStatement: async (
    shopId: string,
    file: File,
    dryRun: boolean,
  ): Promise<StatementImportReport> => {
    const formData = new FormData()
    formData.append('shop_id', shopId)
    formData.append('file', file)
    formData.append('dry_run', String(dryRun))

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
