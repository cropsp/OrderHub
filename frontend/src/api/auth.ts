/**
 * OrderHub CRM — Auth API
 */

import client, { setAccessToken } from './client'

export interface LoginCredentials {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export const authApi = {
  login: async (credentials: LoginCredentials): Promise<TokenResponse> => {
    const { data } = await client.post<TokenResponse>('/auth/login', credentials)
    setAccessToken(data.access_token)
    return data
  },

  refresh: async (): Promise<TokenResponse> => {
    const { data } = await client.post<TokenResponse>('/auth/refresh')
    setAccessToken(data.access_token)
    return data
  },

  logout: async (): Promise<void> => {
    await client.post('/auth/logout')
    setAccessToken(null)
  },
}
