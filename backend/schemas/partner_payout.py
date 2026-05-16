"""
OrderHub CRM — Partner Payout Schemas (PART-1)

Pydantic request/response models for the partner payouts router. Settlements
and payments are immutable (no update schemas); operator deletes and recreates
to correct wrong values.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from schemas.finance import CurrencyAmount


FormulaLiteral = Literal["revenue_items_minus_fees", "net_profit_product_only"]


class PartnerPayoutPreviewRequest(BaseModel):
    formula_type: FormulaLiteral
    percent: Decimal = Field(..., gt=0, le=100)
    period_start: date
    period_end: date
    # Optional disambiguator when the formula returns multiple currency rows.
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class PartnerPayoutPreviewResponse(BaseModel):
    # Populated when currency filter applied OR formula returns exactly one row.
    base_amount: Decimal | None = None
    base_currency: str | None = None
    computed_amount: Decimal | None = None
    # Populated when multi-currency without disambiguator — caller picks.
    available_currencies: list[CurrencyAmount] = Field(default_factory=list)


class PartnerSettlementCreate(BaseModel):
    partner_name: str = Field(..., min_length=1, max_length=200)
    formula_type: FormulaLiteral
    percent: Decimal = Field(..., gt=0, le=100)
    period_start: date
    period_end: date
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: str | None = None


class PartnerSettlementResponse(BaseModel):
    id: UUID
    shop_id: UUID
    partner_name: str
    formula_type: FormulaLiteral
    percent: Decimal
    period_start: date
    period_end: date
    base_amount: Decimal
    base_currency: str
    computed_amount: Decimal
    paid_amount: Decimal
    notes: str | None = None
    created_at: datetime
    created_by_user_id: UUID

    class Config:
        from_attributes = True


class PartnerSettlementListResponse(BaseModel):
    items: list[PartnerSettlementResponse]
    total: int


class PartnerPaymentCreate(BaseModel):
    partner_name: str = Field(..., min_length=1, max_length=200)
    settlement_id: UUID | None = None
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(..., min_length=3, max_length=3)
    paid_at: date
    notes: str | None = None


class PartnerPaymentResponse(BaseModel):
    id: UUID
    shop_id: UUID
    partner_name: str
    settlement_id: UUID | None = None
    amount: Decimal
    currency: str
    paid_at: date
    notes: str | None = None
    created_at: datetime
    created_by_user_id: UUID

    class Config:
        from_attributes = True


class PartnerPaymentListResponse(BaseModel):
    items: list[PartnerPaymentResponse]
    total: int


class PartnerBalance(BaseModel):
    partner_name: str
    currency: str
    total_settled: Decimal
    total_paid: Decimal
    balance_owed: Decimal


class PartnerBalancesResponse(BaseModel):
    items: list[PartnerBalance]


class PartnerNamesResponse(BaseModel):
    items: list[str]
