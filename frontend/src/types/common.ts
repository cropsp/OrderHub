/**
 * OrderHub CRM — Shared TypeScript Types
 */

// ─── Enums ──────────────────────────────────────────────────

export type UserRole = 'owner' | 'manager' | 'designer'

export type ShopPlatform = 'etsy' | 'shopify'

export type OrderStatus =
  | 'new'
  | 'waiting_info'
  | 'info_received'
  | 'design_pending'
  | 'design_ready'
  | 'in_production'
  | 'shipped'
  | 'completed'
  | 'cancelled'

export type AttachmentType = 'mockup' | 'reference' | 'other'

// ─── Models ─────────────────────────────────────────────────

export interface User {
  id: string
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Shop {
  id: string
  name: string
  platform: ShopPlatform
  color: string
  is_active: boolean
  last_synced_at: string | null
  created_at: string
}

export interface Customer {
  id: string
  email: string
  full_name: string
  country: string | null
  created_at: string
}

export interface OrderItem {
  id: string
  order_id: string
  listing_id: string | null
  sku: string | null
  title: string
  quantity: number
  unit_price: number
  currency: string
  variations: string | null
}

export interface OrderStatusHistoryEntry {
  id: string
  order_id: string
  changed_by_id: string
  from_status: string
  to_status: string
  comment: string | null
  changed_at: string
}

export interface Attachment {
  id: string
  order_id: string
  uploaded_by_id: string
  file_name: string
  file_size: number
  mime_type: string
  attachment_type: AttachmentType
  created_at: string
}

export interface Order {
  id: string
  external_id: string
  shop_id: string
  customer_id: string
  status: OrderStatus
  title: string
  total_price: number
  currency: string
  production_cost: number | null
  shipping_np_cost: number | null
  platform_fee: number | null
  shipping_name: string | null
  shipping_phone: string | null
  shipping_street_1: string | null
  shipping_street_2: string | null
  shipping_city: string | null
  shipping_state: string | null
  shipping_zip: string | null
  shipping_country: string | null
  assigned_designer_id: string | null
  assigned_at: string | null
  ttn_number: string | null
  ttn_created_at: string | null
  ttn_printed: boolean
  customer_note: string | null
  custom_info: string | null
  internal_note: string | null
  ordered_at: string
  shipped_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
  // Nested relations (when loaded)
  shop?: Shop
  customer?: Customer
  items?: OrderItem[]
  status_history?: OrderStatusHistoryEntry[]
  attachments?: Attachment[]
}

// ─── Pagination ─────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  limit: number
  pages: number
}

export interface ImportResult {
  imported: number
  skipped: number
  errors: any[]
}
