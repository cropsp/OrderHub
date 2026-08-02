"""
OrderHub CRM — BOM Schemas

MAT-3: request/response shapes for the Bill-of-Materials editor.

`BomItemRead.line_cost` and `BomCostBreakdown` are denormalized at serialize
time from the joined Material (current_unit_cost, currency, waste_percent).
`material_*` fields are populated by the service layer when projecting BomItem
into the read schema; pattern mirrors `MaterialReceiptRead.effective_unit_cost`
in schemas/material.py:119-123.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BomItemCreate(BaseModel):
    """One recipe line in the PUT payload."""

    material_id: uuid.UUID
    qty_per_unit: Decimal = Field(..., gt=0)
    notes: Optional[str] = Field(None, max_length=500)


class BomReplaceRequest(BaseModel):
    """Full recipe replacement payload.

    Empty list is valid — means "clear the recipe". Duplicate material_id
    rows are rejected (caller should sum quantities into one row).
    """

    items: list[BomItemCreate]

    @model_validator(mode="after")
    def _no_duplicate_materials(self) -> "BomReplaceRequest":
        seen: set[uuid.UUID] = set()
        for item in self.items:
            if item.material_id in seen:
                raise ValueError(
                    f"Duplicate material_id in BOM payload: {item.material_id}"
                )
            seen.add(item.material_id)
        return self


class BomItemRead(BaseModel):
    """Read projection. material_* fields are hydrated by the service from
    the joined Material relationship; line_cost is computed at serialize."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    material_id: uuid.UUID
    qty_per_unit: Decimal
    notes: Optional[str]
    material_name: str = ""
    material_unit: str = ""
    material_currency: str = ""
    material_current_unit_cost: Decimal = Decimal("0")
    # BOM-WASTE-1: denormalized so line_cost can apply the same waste allowance
    # shipment books, and so the editor can price an un-saved draft row whose
    # material is soft-deleted (those are absent from the active-materials
    # picker, so `fallback` is the frontend's only source — BomEditor.tsx:41-53).
    # Not money: classified "neutral" in tests/test_money_field_completeness.py,
    # and deliberately NOT stripped by routers/products.py:_strip_bom_costs.
    material_waste_percent: Decimal = Decimal("0")
    material_is_active: bool = True
    line_cost: Decimal = Decimal("0")

    @model_validator(mode="after")
    def _compute_line_cost(self) -> "BomItemRead":
        """Waste-inclusive, matching order_consumption_service.py:118-123.

        ROUND_HALF_UP to agree with the booked-COGS path; the previous bare
        `.quantize()` used the decimal context default (ROUND_HALF_EVEN), which
        disagreed on exact-half kopecks (190.425 → 190.42 vs 190.43).
        """
        waste_factor = Decimal("1") + (
            self.material_waste_percent / Decimal("100")
        )
        self.line_cost = (
            self.qty_per_unit * waste_factor * self.material_current_unit_cost
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return self


class BomCostBreakdown(BaseModel):
    """One row per distinct currency in the recipe. No FX conversion in v1
    (Known Limitation #1 — material currency is UAH-only today)."""

    currency: str
    amount: Decimal


class BomReadResponse(BaseModel):
    items: list[BomItemRead]
    cost: list[BomCostBreakdown]
    # True if any BomItem references a soft-deleted Material. Frontend uses
    # it to render a recipe-level warning banner.
    has_inactive_material: bool
