from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, Field, ConfigDict
from models.packaging import PackagingType


class PackagingBoxBase(BaseModel):
    name: str = Field(..., max_length=100)
    packaging_type: PackagingType = PackagingType.BOX
    inner_length_mm: int = Field(..., gt=0)
    inner_width_mm: int = Field(..., gt=0)
    inner_height_mm: int = Field(..., gt=0)
    max_thickness_mm: Optional[int] = Field(None, gt=0)
    max_weight_g: int = Field(..., gt=0)
    tare_weight_g: int = Field(0, ge=0)
    sort_order: int = 0


class PackagingBoxCreate(PackagingBoxBase):
    pass


class PackagingBoxUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    packaging_type: Optional[PackagingType] = None
    inner_length_mm: Optional[int] = Field(None, gt=0)
    inner_width_mm: Optional[int] = Field(None, gt=0)
    inner_height_mm: Optional[int] = Field(None, gt=0)
    max_thickness_mm: Optional[int] = Field(None, gt=0)
    max_weight_g: Optional[int] = Field(None, gt=0)
    tare_weight_g: Optional[int] = Field(None, ge=0)
    sort_order: Optional[int] = None


class PackagingBoxRead(PackagingBoxBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class PackagingBoxSummary(BaseModel):
    """Minimal projection embedded in OrderResponse (PKG-1)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    inner_length_mm: int
    inner_width_mm: int
    inner_height_mm: int
    tare_weight_g: int
