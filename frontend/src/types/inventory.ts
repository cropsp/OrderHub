export type PackagingType = 'BOX' | 'ENVELOPE';

export type StockMovementReason =
  | 'initial_stock'
  | 'restock'
  | 'ttn_create'
  | 'ttn_delete'
  | 'adjustment';

export interface PackagingBox {
  id: string;
  // WH-1: the paired Material that carries this box's cost, receipts and
  // supplier article. The geometry lives here; the money lives there.
  material_id: string;
  name: string;
  packaging_type: PackagingType;
  inner_length_mm: number;
  inner_width_mm: number;
  inner_height_mm: number;
  max_thickness_mm: number | null;
  max_weight_g: number;
  tare_weight_g: number;
  sort_order: number;
  stock_quantity: number;
  low_stock_threshold: number;
  created_at: string;
  updated_at: string;
}

export interface PackagingBoxCreate {
  name: string;
  packaging_type: PackagingType;
  inner_length_mm: number;
  inner_width_mm: number;
  inner_height_mm: number;
  max_thickness_mm?: number | null;
  max_weight_g: number;
  tare_weight_g?: number;
  sort_order?: number;
  initial_quantity?: number;
  low_stock_threshold?: number;
}

export interface PackagingBoxUpdate {
  name?: string;
  packaging_type?: PackagingType;
  inner_length_mm?: number;
  inner_width_mm?: number;
  inner_height_mm?: number;
  max_thickness_mm?: number | null;
  max_weight_g?: number;
  tare_weight_g?: number;
  sort_order?: number;
  low_stock_threshold?: number;
}

export interface RestockRequest {
  quantity: number;
  note?: string | null;
}

export interface StockMovement {
  id: string;
  box_id: string;
  order_id: string | null;
  delta: number;
  reason: StockMovementReason;
  note: string | null;
  user_id: string;
  created_at: string;
}

export interface ProductVariant {
  id: string;
  product_id: string;
  sku: string | null;
  variant_name: string | null;
  weight_g: number;
  length_mm: number;
  width_mm: number;
  height_mm: number;
  price: number | string | null;
  cost_price: number | string | null;
  stock_quantity: number;
  is_active: boolean;
  volume_cm3?: number;
}

export interface Product {
  id: string;
  shop_id: string;
  title: string;
  description: string | null;
  external_ref?: string | null;
  is_active: boolean;
  variants: ProductVariant[];
  /**
   * Path to the authenticated image route when the product has an image, else
   * null. Not usable as a bare <img src> — the JWT is an in-memory header, so
   * the browser would send it unauthenticated. Fetch it as a blob instead.
   */
  image_url: string | null;
}

export type ProductRead = Product;

export interface ProductVariantCreate {
  sku?: string | null;
  variant_name?: string | null;
  weight_g: number;
  length_mm: number;
  width_mm: number;
  height_mm: number;
  price?: number | string | null;
  cost_price?: number | string | null;
  stock_quantity?: number;
  is_active?: boolean;
}

export interface ProductVariantPatch extends Partial<ProductVariantCreate> {
  id?: string;
}

export interface ProductCreate {
  title: string;
  description?: string | null;
  variants: ProductVariantCreate[];
}

export interface ProductUpdate {
  title?: string;
  description?: string | null;
  is_active?: boolean;
  variants?: ProductVariantPatch[];
}

// WH-1: PACKAGING materials back a packaging box (name and category are owned by
// the packaging page, which is why neither is editable from the material form).
export type MaterialCategory = 'MATERIAL' | 'PACKAGING';

// MAT-1: direct materials catalog. Stock/cost fields are read-only display
// in this sprint and become editable in MAT-2 once receipts exist.
export interface Material {
  id: string;
  name: string;
  unit: string;
  currency: string;
  // Decimal columns are serialized as strings by FastAPI to preserve precision.
  current_unit_cost: string;
  stock_quantity: string;
  low_stock_threshold: string;
  waste_percent: string;
  supplier_name: string | null;
  // MAT-6: the supplier's article (артикул) — the key that ties one material
  // across invoices. Nullable: not every item has a supplier code.
  supplier_sku: string | null;
  notes: string | null;
  is_active: boolean;
  category: MaterialCategory;
  // WH-1: false → contributes cost to an order, never moves stock (services such
  // as laser cutting or sewing, modelled as materials).
  is_stock_tracked: boolean;
  created_at: string;
  updated_at: string;
}

export interface MaterialCreate {
  name: string;
  unit: string;
  currency: string;
  supplier_name?: string | null;
  supplier_sku?: string | null;
  notes?: string | null;
  // Omitted → the API defaults to a stock-tracked MATERIAL.
  category?: MaterialCategory;
  is_stock_tracked?: boolean;
}

// currency intentionally absent — locked at creation.
// MAT-2: low_stock_threshold and waste_percent become editable. stock_quantity
// and current_unit_cost remain read-only (mutated only via receipts/adjustments).
export interface MaterialUpdate {
  name?: string;
  unit?: string;
  supplier_name?: string | null;
  supplier_sku?: string | null;
  notes?: string | null;
  low_stock_threshold?: number | string;
  waste_percent?: number | string;
  // WH-1. `category` is deliberately absent from the form: on a material paired
  // with a packaging box the API answers 409 for both it and `name`.
  is_stock_tracked?: boolean;
}

// MAT-2: receipts + ledger + adjustments.

export type MaterialMovementReason =
  | 'receipt'
  | 'consumption'
  | 'waste'
  | 'adjustment';

export interface MaterialReceipt {
  id: string;
  material_id: string;
  qty: string;
  unit_cost: string;
  currency: string;
  shipping_cost: string | null;
  is_initial: boolean;
  supplier: string | null;
  invoice_no: string | null;
  received_at: string;
  notes: string | null;
  user_id: string;
  created_at: string;
  effective_unit_cost: string;
}

export interface MaterialReceiptCreate {
  qty: number | string;
  unit_cost: number | string;
  currency: string;
  shipping_cost?: number | string | null;
  supplier?: string | null;
  invoice_no?: string | null;
  received_at?: string | null;
  notes?: string | null;
}

export interface MaterialReceiptResponse {
  material: Material;
  receipt: MaterialReceipt;
}

export interface MaterialMovement {
  id: string;
  material_id: string;
  delta: string;
  reason: MaterialMovementReason;
  order_id: string | null;
  order_code: string | null;
  receipt_id: string | null;
  unit_cost_at_movement: string | null;
  notes: string | null;
  user_id: string;
  created_at: string;
}

export interface MaterialStockAdjustment {
  delta: number | string;
  reason: 'waste' | 'adjustment';
  notes?: string | null;
}

export interface OverheadMaterialReceipt {
  id: string;
  overhead_material_id: string;
  shop_id: string | null;
  shop_name: string | null;
  qty: string | null;
  total_cost: string;
  currency: string;
  supplier: string | null;
  invoice_no: string | null;
  received_at: string;
  notes: string | null;
  user_id: string;
  created_at: string;
}

export interface OverheadMaterialReceiptCreate {
  qty?: number | string | null;
  total_cost: number | string;
  currency: string;
  shop_id?: string | null;
  supplier?: string | null;
  invoice_no?: string | null;
  received_at?: string | null;
  notes?: string | null;
}

// MAT-1: indirect/consumables catalog.
export interface OverheadMaterial {
  id: string;
  name: string;
  unit: string;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OverheadMaterialCreate {
  name: string;
  unit: string;
  notes?: string | null;
}

export interface OverheadMaterialUpdate {
  name?: string;
  unit?: string;
  notes?: string | null;
}

// MAT-3: Bill of Materials. BOM lives at Product level (settled-decision #7),
// one row per (Product, Material) pair. Decimal values serialize as strings.
export interface BomItem {
  id: string;
  product_id: string;
  material_id: string;
  qty_per_unit: string;
  notes: string | null;
  material_name: string;
  material_unit: string;
  material_currency: string;
  material_current_unit_cost: string;
  // BOM-WASTE-1: the material's waste allowance, denormalized so the editor can
  // price a draft row whose material is soft-deleted (those are absent from the
  // active-materials picker, so `fallback` is the only source).
  material_waste_percent: string;
  material_is_active: boolean;
  // WH-1: denormalized so the editor can flag a line that prices into the order
  // but never moves stock. Optional so a response predating WH-1 (or a fixture)
  // reads as tracked rather than as untracked.
  material_is_stock_tracked?: boolean;
  // Waste-inclusive, matching the cost a shipment books. Σ(line_cost) may
  // differ from the recipe total by a kopeck — the total rounds once.
  line_cost: string;
}

export interface BomItemCreate {
  material_id: string;
  qty_per_unit: number | string;
  notes?: string | null;
}

/** One row per distinct currency IN THE RECIPE — the un-converted basis.
 *  A converted figure is never appended here: it would be indistinguishable
 *  from a real same-currency material row and any consumer summing the list
 *  would double-count. See BomCostConverted. */
export interface BomCostBreakdown {
  currency: string;
  amount: string;
}

/** The recipe's whole cost in one target currency (FX-CONVERSION).
 *  `uah_per_usd` is NBU's quote direction — UAH per 1 USD — so a UAH basis was
 *  DIVIDED by it. */
export interface BomCostConverted {
  currency: string;
  converted_cost: string;
  uah_per_usd: string;
  rate_date: string | null;
  rate_source: string | null;
}

export interface BomCostEnvelope {
  basis: BomCostBreakdown[];
  /** Null when no target currency was asked for, the recipe is empty, or some
   *  part of it cannot be converted — `basis` is still the whole truth. */
  converted: BomCostConverted | null;
}

export interface BomReadResponse {
  items: BomItem[];
  cost: BomCostBreakdown[];
  cost_converted: BomCostConverted | null;
  has_inactive_material: boolean;
}
