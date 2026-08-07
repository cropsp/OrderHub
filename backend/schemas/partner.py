"""
OrderHub CRM — Partner & Shop-Partner-Config Schemas (PARTNER-CONFIG-1)

Two surfaces with deliberately different shapes:

  - `/api/partners*` is IDENTITY ONLY — name, active flag, notes. No shop data
    and no money, because it carries no `{shop_id}` and is therefore invisible to
    `tests/test_route_scope_completeness.py`. Keeping money off it is what makes
    that invisibility safe rather than a hole. It is OWNER-only.
  - `/api/shops/{shop_id}/partner-config*` carries the money configuration and IS
    visible to that guard.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from schemas.partner_payout import SelectableBasisLiteral


class PartnerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    notes: str | None = None


class PartnerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    notes: str | None = None


class PartnerResponse(BaseModel):
    id: UUID
    name: str
    is_active: bool
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PartnerListResponse(BaseModel):
    items: list[PartnerResponse]


class ShopPartnerConfigUpsert(BaseModel):
    percent: Decimal = Field(..., gt=0, le=100)
    #: Only the two PARTNER-CONFIG-1 bases are selectable — see the note on
    #: SelectableBasisLiteral in schemas/partner_payout.py for why this is not a
    #: database CHECK constraint.
    basis: SelectableBasisLiteral
    settlement_currency: str = Field(..., min_length=3, max_length=3)
    is_active: bool = True


class ShopPartnerConfigResponse(BaseModel):
    id: UUID
    shop_id: UUID
    partner_id: UUID
    partner_name: str
    percent: Decimal
    basis: SelectableBasisLiteral
    settlement_currency: str
    is_active: bool
    #: period_end of this partner's latest settlement on this shop. The UI
    #: defaults the next settlement's period_start to the day after.
    last_period_end: date | None = None


class ShopPartnerConfigListResponse(BaseModel):
    items: list[ShopPartnerConfigResponse]
