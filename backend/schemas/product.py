from datetime import datetime
from typing import List, Optional
import uuid
from pydantic import BaseModel, Field, ConfigDict


class ProductVariantBase(BaseModel):
    sku: Optional[str] = Field(None, max_length=100)
    variant_name: Optional[str] = Field(None, max_length=255)
    external_ref: Optional[str] = Field(None, max_length=255)
    weight_g: int = Field(..., gt=0)
    length_mm: int = Field(..., gt=0)
    width_mm: int = Field(..., gt=0)
    height_mm: int = Field(..., gt=0)
    is_active: bool = True


class ProductVariantCreate(ProductVariantBase):
    pass


class ProductVariantUpdate(BaseModel):
    sku: Optional[str] = Field(None, max_length=100)
    variant_name: Optional[str] = Field(None, max_length=255)
    external_ref: Optional[str] = Field(None, max_length=255)
    weight_g: Optional[int] = Field(None, gt=0)
    length_mm: Optional[int] = Field(None, gt=0)
    width_mm: Optional[int] = Field(None, gt=0)
    height_mm: Optional[int] = Field(None, gt=0)
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


class ProductCreate(ProductBase):
    variants: List[ProductVariantCreate] = Field(..., min_length=1)


class ProductUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    external_ref: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    # Note: Variants update is usually handled via separate logic or a dedicated endpoint


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shop_id: uuid.UUID
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    variants: List[ProductVariantRead]
