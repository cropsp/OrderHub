from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from models.packaging import PackagingType
from models.stock_movement import StockMovementReason


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
    initial_quantity: int = Field(0, ge=0)
    low_stock_threshold: int = Field(5, ge=0)


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
    low_stock_threshold: Optional[int] = Field(None, ge=0)


class PackagingBoxRead(PackagingBoxBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # WH-1: the paired Material carrying cost/receipts/supplier article. Exposed as
    # the bare id on purpose — nesting the material read model here would drag its
    # Decimal cost fields onto this un-cost-gated router (and, via
    # OrderResponse.packaging, onto every order route), which the money-field guard
    # in tests/test_money_field_completeness.py exists to catch.
    material_id: uuid.UUID
    stock_quantity: int
    low_stock_threshold: int
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


class RestockRequest(BaseModel):
    quantity: int = Field(..., ge=1)
    note: Optional[str] = Field(None, max_length=500)


class StockMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    box_id: uuid.UUID
    order_id: Optional[uuid.UUID]
    delta: int
    reason: StockMovementReason
    note: Optional[str]
    user_id: uuid.UUID
    created_at: datetime
