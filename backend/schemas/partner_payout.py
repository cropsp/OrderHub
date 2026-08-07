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


# Two literals, deliberately. Settlements are immutable historical facts, so a
# RESPONSE must be able to carry all four values forever — a PART-1 row still
# means what it meant. A REQUEST may only carry the two PARTNER-CONFIG-1 bases
# (rule 2: legacy values are readable, not selectable).
#
# This split is where "not selectable" is ENFORCED. It cannot be a CHECK
# constraint on shop_partner_config: PostgreSQL forbids a CHECK that names an
# enum value added in the same transaction, and the migration that adds
# 'turnover'/'profit' is also the one that creates that table. See the migration
# docstring (d7f3a1c85e92).
FormulaLiteral = Literal[
    "revenue_items_minus_fees",
    "net_profit_product_only",
    "turnover",
    "profit",
]
SelectableBasisLiteral = Literal["turnover", "profit"]


class BaseTermDetail(BaseModel):
    """One component of a settlement base, before and after FX conversion.

    Shown in the preview so "why is my base this number" is answerable without
    re-running anything. `converted` equals `amount` when no conversion applied.
    """

    name: str
    currency: str
    amount: Decimal
    converted: Decimal


class BaseQualityPanel(BaseModel):
    """Data-readiness warnings for the previewed period (rule 7).

    Advisory — none of these block a settlement. `fx_blocker` is the exception:
    it is the reason Create WILL 422, surfaced here so the operator sees the
    warnings and the blocker in one round trip instead of two.
    """

    total_orders: int
    orders_missing_cost: int
    orders_missing_platform_fee: int
    etsy_months_without_statement: list[str] = Field(default_factory=list)
    etsy_refunds_unbooked: bool = False
    fx_blocker: str | None = None


class PartnerPayoutPreviewRequest(BaseModel):
    # partner_id drives the overlap check and the config defaults. Optional so a
    # legacy-formula preview (read-only, no config) still works.
    partner_id: UUID | None = None
    formula_type: FormulaLiteral
    percent: Decimal = Field(..., gt=0, le=100)
    period_start: date
    period_end: date
    # Optional disambiguator when a LEGACY formula returns multiple currency rows.
    # Unused by the new bases: their currency is configuration, not a choice.
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class OverlappingSettlement(BaseModel):
    id: UUID
    period_start: date
    period_end: date


class PartnerPayoutPreviewResponse(BaseModel):
    # Populated when currency filter applied OR formula returns exactly one row.
    base_amount: Decimal | None = None
    base_currency: str | None = None
    computed_amount: Decimal | None = None
    # Populated when multi-currency without disambiguator — caller picks.
    available_currencies: list[CurrencyAmount] = Field(default_factory=list)
    # PARTNER-CONFIG-1
    fx_rate_used: Decimal | None = None
    terms: list[BaseTermDetail] = Field(default_factory=list)
    quality: BaseQualityPanel | None = None
    #: Settlements of the same (shop, partner) whose period overlaps this one.
    #: Non-empty means Create will be refused with a 422.
    overlapping: list[OverlappingSettlement] = Field(default_factory=list)
    #: period_end of this partner's latest settlement on this shop; the UI
    #: defaults the next period_start to the day after it.
    last_period_end: date | None = None


class PartnerSettlementCreate(BaseModel):
    partner_id: UUID
    formula_type: SelectableBasisLiteral
    percent: Decimal = Field(..., gt=0, le=100)
    period_start: date
    period_end: date
    notes: str | None = None


class PartnerSettlementResponse(BaseModel):
    id: UUID
    shop_id: UUID
    partner_id: UUID
    partner_name: str
    formula_type: FormulaLiteral
    percent: Decimal
    period_start: date
    period_end: date
    base_amount: Decimal
    base_currency: str
    computed_amount: Decimal
    fx_rate_used: Decimal | None = None
    paid_amount: Decimal
    notes: str | None = None
    created_at: datetime
    created_by_user_id: UUID

    class Config:
        from_attributes = True


class SettlementStaleness(BaseModel):
    """One recomputed unpaid settlement (rule 8). Read-only, never persisted."""

    settlement_id: UUID
    stale: bool
    recomputed_base_amount: Decimal | None = None
    reason: str | None = None


class SettlementStalenessResponse(BaseModel):
    items: list[SettlementStaleness]
    checked_count: int
    #: True when more open settlements exist than `limit` allowed checking.
    truncated: bool


class PartnerSettlementListResponse(BaseModel):
    items: list[PartnerSettlementResponse]
    total: int


class PartnerPaymentCreate(BaseModel):
    partner_id: UUID
    settlement_id: UUID | None = None
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(..., min_length=3, max_length=3)
    paid_at: date
    notes: str | None = None


class PartnerPaymentResponse(BaseModel):
    id: UUID
    shop_id: UUID
    partner_id: UUID
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
    partner_id: UUID
    partner_name: str
    currency: str
    total_settled: Decimal
    total_paid: Decimal
    balance_owed: Decimal


class PartnerBalancesResponse(BaseModel):
    items: list[PartnerBalance]


class PartnerNamesResponse(BaseModel):
    items: list[str]
