from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import uuid
from pydantic import BaseModel, Field, ConfigDict


class ProductVariantBase(BaseModel):
    sku: Optional[str] = Field(None, max_length=100)
    variant_name: Optional[str] = Field(None, max_length=255)
    external_ref: Optional[str] = Field(None, max_length=255)
    weight_g: int = Field(..., ge=0)
    length_mm: int = Field(..., ge=0)
    width_mm: int = Field(..., ge=0)
    height_mm: int = Field(..., ge=0)
    price: Optional[Decimal] = Field(None, ge=0)
    cost_price: Optional[Decimal] = Field(None, ge=0)
    stock_quantity: int = Field(0, ge=0)
    is_active: bool = True


class ProductVariantCreate(ProductVariantBase):
    weight_g: int = Field(..., gt=0)
    length_mm: int = Field(..., gt=0)
    width_mm: int = Field(..., gt=0)
    height_mm: int = Field(..., gt=0)


class ProductVariantUpdate(BaseModel):
    sku: Optional[str] = Field(None, max_length=100)
    variant_name: Optional[str] = Field(None, max_length=255)
    external_ref: Optional[str] = Field(None, max_length=255)
    weight_g: Optional[int] = Field(None, gt=0)
    length_mm: Optional[int] = Field(None, gt=0)
    width_mm: Optional[int] = Field(None, gt=0)
    height_mm: Optional[int] = Field(None, gt=0)
    price: Optional[Decimal] = Field(None, ge=0)
    cost_price: Optional[Decimal] = Field(None, ge=0)
    stock_quantity: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class ProductVariantRead(ProductVariantBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    volume_cm3: float
    created_at: datetime
    updated_at: datetime


class ProductBase(BaseModel):
    title: str = Field(..., max_length=500)
    description: Optional[str] = None
    external_ref: Optional[str] = Field(None, max_length=255)
    is_active: bool = True

    # WH-5: the box this product ships in. On ProductBase (not alongside image_url
    # below) because it IS settable through JSON — unlike image_url, which is
    # file-backed. A bare id, never a nested box read model: PackagingBoxRead
    # carries Decimal counters that would land on this un-cost-gated router.
    default_packaging_box_id: Optional[uuid.UUID] = None


class ProductCreate(ProductBase):
    variants: List[ProductVariantCreate] = Field(..., min_length=1)


class ProductVariantPatch(ProductVariantUpdate):
    """Variant update payload that carries the variant id for matching."""
    id: Optional[uuid.UUID] = None


class ProductUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    external_ref: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    variants: Optional[List["ProductVariantPatch"]] = None

    # WH-5. Its own line because this schema is a standalone BaseModel, not a
    # ProductBase subclass. An explicit `null` clears the default — update_product
    # dumps with exclude_unset=True, which keeps a passed None and drops an
    # unmentioned field.
    default_packaging_box_id: Optional[uuid.UUID] = None


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shop_id: uuid.UUID
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    variants: List[ProductVariantRead]

    # PC-F-1 — path to the authenticated image route when the product has an
    # image, else None. Deliberately not on ProductBase: it is file-backed and
    # must not be settable through ProductCreate/ProductUpdate JSON.
    image_url: Optional[str] = None
