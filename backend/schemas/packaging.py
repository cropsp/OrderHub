from datetime import datetime
from decimal import Decimal
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

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
    # WH-2: `initial_quantity` is gone. It handed a box units with no price behind
    # them; stock now arrives only through a material receipt, which carries cost.
    # The threshold is stored on the paired material but still entered here, since
    # the packaging page is the one surface where boxes are managed.
    #
    # extra="forbid" so a client still sending initial_quantity gets a loud 422
    # instead of Pydantic's default silent drop — a stale form that appears to work
    # while the box quietly stays at zero is the worse failure of the two.
    model_config = ConfigDict(extra="forbid")

    low_stock_threshold: Decimal = Field(Decimal(5), ge=0)


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
    # Decimal, not int: the target column is materials.low_stock_threshold,
    # Numeric(12,2). An int here would silently truncate a fractional threshold.
    low_stock_threshold: Optional[Decimal] = Field(None, ge=0)


class PackagingBoxRead(PackagingBoxBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # WH-1: the paired Material carrying cost/receipts/supplier article. Exposed as
    # the bare id on purpose — nesting the material read model here would drag its
    # Decimal cost fields onto this un-cost-gated router (and, via
    # OrderResponse.packaging, onto every order route), which the money-field guard
    # in tests/test_money_field_completeness.py exists to catch.
    material_id: uuid.UUID
    # WH-2: read through PackagingBox's properties off the paired material, which is
    # where these counters now live. Decimal because materials.stock_quantity is
    # Numeric(12,2) — the JSON goes from `15` to `"15.00"`, and the frontend type
    # mirrors Material's string-typed counters accordingly.
    #
    # Both names are classified "neutral" in tests/test_money_field_completeness.py,
    # which is what keeps this un-cost-gated router (and ParcelEstimate, which nests
    # this model) out of the money-surface table. Never add a cost-named field here.
    stock_quantity: Decimal
    low_stock_threshold: Decimal
    # Surfaced so the packaging page can flag an archived box; the picker and the
    # parcel calculator filter on it server-side. Precedent for the flattened
    # material_* shape: BomItemRead.material_is_stock_tracked.
    material_is_active: bool
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


# WH-2 removed `RestockRequest` (the quantity-only restock endpoint it fed is gone —
# replenishment is a material receipt now, so it carries a price) and
# `StockMovementRead` (the packaging ledger is frozen; it had no route and no reader
# even before that).
