"""
OrderHub CRM — Materials Schemas

MAT-1: Catalog (Material/OverheadMaterial Create/Update/Read).
MAT-2: Receipts + ledger + adjustments schemas; MaterialUpdate gains
       low_stock_threshold and waste_percent.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.material import MaterialMovementReason


# ---- Material (direct) ----


class MaterialBase(BaseModel):
    name: str = Field(..., max_length=200)
    unit: str = Field(..., max_length=20)
    supplier_name: Optional[str] = Field(None, max_length=200)
    # MAT-6: supplier's article (артикул). Inherited by MaterialCreate + MaterialRead.
    supplier_sku: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class MaterialCreate(MaterialBase):
    # ISO 4217; locked at creation per design doc settled-decision #12.
    currency: str = Field(..., min_length=3, max_length=3)


class MaterialUpdate(BaseModel):
    # currency / current_unit_cost / stock_quantity intentionally absent —
    # MAT-2 rule #10: only via receipts / adjustments.
    name: Optional[str] = Field(None, max_length=200)
    unit: Optional[str] = Field(None, max_length=20)
    supplier_name: Optional[str] = Field(None, max_length=200)
    supplier_sku: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    low_stock_threshold: Optional[Decimal] = Field(None, ge=0)
    waste_percent: Optional[Decimal] = Field(None, ge=0, le=100)


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


# ---- MAT-2: Material receipts + ledger ----


class MaterialReceiptCreate(BaseModel):
    qty: Decimal = Field(..., gt=0)
    unit_cost: Decimal = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=3)
    shipping_cost: Optional[Decimal] = Field(None, ge=0)
    supplier: Optional[str] = Field(None, max_length=200)
    invoice_no: Optional[str] = Field(None, max_length=100)
    received_at: Optional[datetime] = None
    notes: Optional[str] = None


class MaterialReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    material_id: uuid.UUID
    qty: Decimal
    unit_cost: Decimal
    currency: str
    shipping_cost: Optional[Decimal]
    is_initial: bool
    supplier: Optional[str]
    invoice_no: Optional[str]
    received_at: datetime
    notes: Optional[str]
    user_id: uuid.UUID
    created_at: datetime
    effective_unit_cost: Decimal = Decimal("0")

    @model_validator(mode="after")
    def _compute_effective(self) -> "MaterialReceiptRead":
        ship = self.shipping_cost if self.shipping_cost is not None else Decimal("0")
        self.effective_unit_cost = (self.qty * self.unit_cost + ship) / self.qty
        return self


class MaterialReceiptResponse(BaseModel):
    """Wrapper returned by POST /api/materials/{id}/receipts."""

    material: MaterialRead
    receipt: MaterialReceiptRead


class MaterialMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    material_id: uuid.UUID
    delta: Decimal
    reason: MaterialMovementReason
    order_id: Optional[uuid.UUID]
    order_code: Optional[str] = None  # joined; NULL in MAT-2 (no consumption yet)
    receipt_id: Optional[uuid.UUID]
    unit_cost_at_movement: Optional[Decimal]
    notes: Optional[str]
    user_id: uuid.UUID
    created_at: datetime


class MaterialStockAdjustment(BaseModel):
    delta: Decimal = Field(...)
    reason: Literal["waste", "adjustment"]
    notes: Optional[str] = None

    @field_validator("delta")
    @classmethod
    def _non_zero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("delta must be non-zero")
        return v


# ---- MAT-2: Overhead material receipts ----


class OverheadMaterialReceiptCreate(BaseModel):
    qty: Optional[Decimal] = Field(None, ge=0)
    total_cost: Decimal = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=3)
    shop_id: Optional[uuid.UUID] = None
    supplier: Optional[str] = Field(None, max_length=200)
    invoice_no: Optional[str] = Field(None, max_length=100)
    received_at: Optional[datetime] = None
    notes: Optional[str] = None


class OverheadMaterialReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    overhead_material_id: uuid.UUID
    shop_id: Optional[uuid.UUID]
    shop_name: Optional[str] = None  # joined for UI convenience
    qty: Optional[Decimal]
    total_cost: Decimal
    currency: str
    supplier: Optional[str]
    invoice_no: Optional[str]
    received_at: datetime
    notes: Optional[str]
    user_id: uuid.UUID
    created_at: datetime


# ---- MAT-6: receipts grouped by supplier invoice ----
#
# Subclasses rather than new models, so the per-material read shapes above stay
# untouched and every numeric field they carry remains already-classified in
# tests/test_money_field_completeness.py. The joined display-name pattern
# mirrors MaterialMovementRead.order_code and OverheadMaterialReceiptRead.shop_name.


class InvoiceMaterialReceiptRead(MaterialReceiptRead):
    material_name: Optional[str] = None  # joined


class InvoiceOverheadReceiptRead(OverheadMaterialReceiptRead):
    overhead_material_name: Optional[str] = None  # joined


class InvoiceReceiptsRead(BaseModel):
    """Every line booked under one supplier invoice, across both ledgers.

    A real invoice mixes direct materials with overhead lines (cutting service,
    finishing compound), so both blocks are returned. No totals: summing is the
    reader's job — the lines may span currencies, and a summed field here would
    be a new money surface for no gain.
    """

    invoice_no: str
    material_receipts: List[InvoiceMaterialReceiptRead]
    overhead_receipts: List[InvoiceOverheadReceiptRead]
