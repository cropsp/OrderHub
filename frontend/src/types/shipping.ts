import { PackagingBox } from "./inventory";

export interface ParcelEstimate {
  total_weight_g: number;
  total_volume_cm3: number;
  selected_packaging: PackagingBox | null;
  packaging_type: 'BOX' | 'ENVELOPE' | null;
  parcel_length_mm: number;
  parcel_width_mm: number;
  parcel_height_mm: number;
  volumetric_weight_g: number;
  chargeable_weight_g: number;
  unlinked_items_count: number;
  warnings: string[];
}
