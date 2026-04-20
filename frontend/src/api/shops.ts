import client from './client'

import type { ShopListItem } from '@/types/shop'

export const shopsApi = {
  list: async (): Promise<ShopListItem[]> => {
    const { data } = await client.get<ShopListItem[]>('/shops')
    return data
  },
}
