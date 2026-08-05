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
  /** SHOP-FEE-1: total effective transaction fee, percent. A string because it
   *  is a Decimal server-side — parse before arithmetic. null means either "no
   *  rate configured" or "you may not see it" (nulled without VIEW_COSTS). */
  fee_percent: string | null
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
  // ORDER-CARD-1 Part 2: linked-product image (PC-F-1). Both null for custom
  // lines and products without an image. image_url is the presence flag +
  // `/api/products/{id}/image`; product_id is the fetch key for useProductImage.
  product_id: string | null
  image_url: string | null
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
  // Human Shopify order name (e.g. "91890_1816"); null for Etsy/manual orders.
  order_number: string | null
  shop_id: string
  customer_id: string
  status: OrderStatus
  title: string
  total_price: number
  currency: string
  production_cost: number | null
  // MAT-4: BOM-driven cost snapshot, populated when the order transitions to
  // SHIPPED. Coexists with manual `production_cost` (Phase A — design §6.2).
  computed_production_cost: number | null
  /** FX-CONVERSION: how computed_production_cost was derived, frozen at ship.
   *  The rate is UAH per 1 USD, so cost = basis / rate. A null rate beside a
   *  non-null cost means no conversion was needed (same-currency order). All
   *  three are censored with the cost for callers without view_costs. */
  cogs_fx_rate: number | null
  cogs_basis_amount: number | null
  cogs_basis_currency: string | null
  shipping_np_cost: number | null
  platform_fee: number | null
  /** ORDER-SHIPPING-1/2: what the customer paid, decomposed —
   *    total_price = Σ(qty × unit_price) − discount_total + shipping_revenue + tax_total
   *  `shipping_revenue` is what the CUSTOMER was charged, the revenue twin of
   *  `shipping_np_cost` above (what we pay Nova Poshta). `discount_total` is
   *  positive; subtract it when rendering.
   *  null means UNKNOWN, not 0 — Etsy/manual orders carry no such figures, and
   *  neither do Shopify orders imported before the backfill ran. Never render a
   *  null as 0.00; see DetailFinance's derived-row fallback. */
  shipping_revenue: number | null
  /** ORDER-SHIPPING-2: how much of the shipping charge was given away, positive.
   *  NOT a term in the identity above — `shipping_revenue` is already net of it,
   *  so subtracting it again double-counts. Render it as an annotation on the
   *  shipping figure, never as its own arithmetic row. It exists because a 0.00
   *  shipping charge cannot say whether a promo was given. */
  shipping_discount: number | null
  /** The discount on the GOODS only. Before ORDER-SHIPPING-2 this also folded in
   *  shipping promos, which made a free-shipping order look like a markdown. */
  discount_total: number | null
  tax_total: number | null
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

  // PKG-1 — operator-chosen packaging
  packaging_id?: string | null
  packaging?: PackagingBoxSummary | null

  // Nested relations (when loaded)
  shop?: Shop
  customer?: Customer
  items?: OrderItem[]
  status_history?: OrderStatusHistoryEntry[]
  attachments?: Attachment[]
}

export interface PackagingBoxSummary {
  id: string
  name: string
  inner_length_mm: number
  inner_width_mm: number
  inner_height_mm: number
  tare_weight_g: number
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

/** STATEMENT-IMPORT: an order the statement charges for, summed.
 *  Used both for orders this shop does not have (nothing was written) and for
 *  orders whose fee came out negative because the period that charged it has
 *  not been imported. */
export interface StatementUnmatchedOrder {
  order_external_id: string
  platform_fee_amount: number
}

/** An unmatched order number plus the signal that tells the two causes apart.
 *  `has_sale_row` = the statement itself sold this id (in this file or any
 *  imported period), so it is a real Etsy order missing from OrderHub. False =
 *  either its sale month was never imported, or the number is not an order
 *  number at all. Not carried on credit_only_orders, where it is always false
 *  by definition. */
export interface StatementUnmatchedEntry extends StatementUnmatchedOrder {
  has_sale_row: boolean
}

/** An order whose existing platform_fee the statement replaced. The statement is
 *  what Etsy actually charged, so it wins over a hand-entered estimate — the
 *  opposite of the flat-rate path, and never silent. */
export interface StatementFeeOverride {
  order_external_id: string
  previous_platform_fee: number
  statement_platform_fee: number
}

/** Proof, computed off the rows the import actually stored, that the three
 *  booked buckets account for every cost row exactly. An unbalanced import
 *  aborts server-side, so `balanced` is always true in a report you can see —
 *  it is shown anyway, because a checksum nobody displays proves nothing. */
export interface StatementPartitionChecksum {
  stored_line_count: number
  booked_cost_total: number
  /** THIS period's fee contribution — not the sum of order.platform_fee, which
   *  aggregates every period imported so far. */
  platform_fee_total: number
  unclassified_buckets: string[]
  balanced: boolean
}

/** Mirrors backend schemas/etsy_statement.py StatementImportReport. */
export interface StatementImportReport {
  /** True: a rehearsal that was rolled back. Every other field is what a real
   *  import would have reported — it is the same code path either way. */
  dry_run: boolean

  period: string
  source_filename: string
  file_sha256: string
  identical_file: boolean

  lines_imported: number
  lines_replaced: number

  orders_matched: number
  orders_unmatched: number
  unmatched_orders: StatementUnmatchedEntry[]
  fee_overrides: StatementFeeOverride[]
  credit_only_orders: StatementUnmatchedOrder[]

  ads_overhead_amount: number
  account_fee_overhead_amount: number

  checksum: StatementPartitionChecksum

  sales_count: number
  statement_base_amount: number
  refunds_count: number
  refunds_amount: number
  deposits_count: number
  deposits_amount: number
}
