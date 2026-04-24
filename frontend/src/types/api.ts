import type { AxiosError } from 'axios'

export interface ApiErrorBody {
  detail?: string
}

export type ApiError = AxiosError<ApiErrorBody>

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const body = (error as ApiError).response?.data
    if (body?.detail) return body.detail
  }
  return fallback
}
