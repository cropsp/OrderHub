import type { OrderListItem } from '@/types/order'

/** Recipient-first display name: shipping_name → customer_name → "Unknown". */
export function orderDisplayName(
  order: Pick<OrderListItem, 'shipping_name' | 'customer_name'>,
): string {
  return order.shipping_name?.trim() || order.customer_name?.trim() || 'Unknown'
}
