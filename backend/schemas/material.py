"""
OrderHub CRM — Materials Schemas (MAT-1)

Catalog-only. Stock/receipt fields hidden from Create per task §scope rule #5;
defaults apply server-side and these fields surface on Read for future use.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---- Material (direct) ----


class MaterialBase(BaseModel):
    name: str = Field(..., max_length=200)
    unit: str = Field(..., max_length=20)
    supplier_name: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None


class MaterialCreate(MaterialBase):
    # ISO 4217; locked at creation per design doc settled-decision #12.
    currency: str = Field(..., min_length=3, max_length=3)


class MaterialUpdate(BaseModel):
    # currency intentionally absent — read-only post-creation.
    # Pydantic v2 silently ignores it if a client sends it (matches Shop/Packaging convention).
    name: Optional[str] = Field(None, max_length=200)
    unit: Optional[str] = Field(None, max_length=20)
    supplier_name: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None


class MaterialRead(MaterialBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    currency: str
    current_unit_cost: Decimal
    stock_quantity: Decimal
    low_stock_threshold: Decimal
    waste_percent: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---- OverheadMaterial (indirect) ----


class OverheadMaterialBase(BaseModel):
    name: str = Field(..., max_length=200)
    unit: str = Field(..., max_length=50)
    notes: Optional[str] = None


class OverheadMaterialCreate(OverheadMaterialBase):
    pass


class OverheadMaterialUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    unit: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None


class OverheadMaterialRead(OverheadMaterialBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
