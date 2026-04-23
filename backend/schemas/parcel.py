from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from uuid import UUID
from schemas.packaging import PackagingBoxRead

class ParcelEstimate(BaseModel):
    total_weight_g: int = Field(..., description="Sum of items weight + tare weight of packaging")
    total_volume_cm3: float = Field(..., description="Raw sum of item volumes")
    selected_packaging: Optional[PackagingBoxRead] = Field(None, description="The selected Box or Envelope")
    packaging_type: Optional[Literal["BOX", "ENVELOPE"]] = None
    parcel_length_mm: int
    parcel_width_mm: int
    parcel_height_mm: int
    volumetric_weight_g: int = Field(..., description="(L_cm * W_cm * H_cm) / 4 [grams]")
    chargeable_weight_g: int = Field(..., description="max(total_weight_g, volumetric_weight_g)")
    unlinked_items_count: int = Field(..., description="Count of items without dimension snapshots")
    warnings: List[str] = []

    class Config:
        from_attributes = True
