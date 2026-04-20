import type { Shop } from './common'

export interface ShopListItem extends Shop {
  updated_at: string
  has_shopify_token: boolean
  has_np_token: boolean
}
