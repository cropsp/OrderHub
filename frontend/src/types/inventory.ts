export type PackagingType = 'BOX' | 'ENVELOPE';

export interface PackagingBox {
  id: string;
  shop_id: string;
  name: string;
  packaging_type: PackagingType;
  inner_length_mm: number;
  inner_width_mm: number;
  inner_height_mm: number;
  max_thickness_mm: number | null;
  max_weight_g: number;
  tare_weight_g: number;
  sort_order: number;
  created_at: string;
  updated_at: string;
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
