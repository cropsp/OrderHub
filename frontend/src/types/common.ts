/**
 * OrderHub CRM — Shared TypeScript Types
 */

// ─── Enums ──────────────────────────────────────────────────

export type ShopPlatform = 'etsy' | 'shopify' | 'manual'

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

export type { User } from './user'

export interface Shop {
  id: string
  name: string
  platform: ShopPlatform
  color: string
  is_active: boolean
  last_synced_at: string | null
  np_sender_name: string | null
  np_sender_phone: string | null
  np_sender_city_ref: string | null
  np_sender_warehouse_ref: string | null
  np_default_description: string | null
  np_default_weight_kg: number
  np_default_volume_m3: number
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
  product_variant_id: string | null
  snapshot_weight_g: number | null
  snapshot_length_mm: number | null
  snapshot_width_mm: number | null
  snapshot_height_mm: number | null
  snapshot_title: string | null
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
  shipping_city_ref: string | null
  shipping_warehouse_ref: string | null
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
  
  // Calculated parcel fields
  computed_parcel_weight_g?: number | null
  computed_parcel_length_mm?: number | null
  computed_parcel_width_mm?: number | null
  computed_parcel_height_mm?: number | null
  computed_packaging_box_id?: string | null
  parcel_override: boolean

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
