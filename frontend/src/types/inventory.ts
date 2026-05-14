export type PackagingType = 'BOX' | 'ENVELOPE';

export type StockMovementReason =
  | 'initial_stock'
  | 'restock'
  | 'ttn_create'
  | 'ttn_delete'
  | 'adjustment';

export interface PackagingBox {
  id: string;
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
  is_active: boolean;
  variants: ProductVariant[];
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
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MaterialCreate {
  name: string;
  unit: string;
  currency: string;
  supplier_name?: string | null;
  notes?: string | null;
}

// currency intentionally absent — locked at creation.
export interface MaterialUpdate {
  name?: string;
  unit?: string;
  supplier_name?: string | null;
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
