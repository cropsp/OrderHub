"""
OrderHub CRM — PartnerSettlement Model (PART-1)

Frozen snapshot of a partner payout computation. Created via the settlements
calculator; base_amount and computed_amount are captured at insert time and
never recomputed (audit-integrity pattern, same as MAT-2 MaterialMovement).
Immutable + delete-and-recreate; no edit endpoint.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from models.base import Base, UUIDPrimaryKeyMixin


class PartnerSettlementFormula(str, PyEnum):
    """Formula used to compute a partner settlement's base_amount.

    Backed by the PG enum `partner_settlement_formula`. The first two values are
    LEGACY (PART-1): they must keep deserialising forever — settlements are
    immutable historical facts — but they are not selectable for new settlements
    or configs. That split is enforced by the two Literals in
    `schemas/partner_payout.py`, not by a DB constraint.

    Both legacy values pay the partner on revenue that was later refunded
    (PARTNER-REFUND-BASE). The two PARTNER-CONFIG-1 values below fix that by
    subtracting refunds dated in the period, and additionally exclude the
    discount the shop funded. Neither legacy value was redefined — an old
    settlement still means what it meant when it was written.
    """

    REVENUE_ITEMS_MINUS_FEES = "revenue_items_minus_fees"
    NET_PROFIT_PRODUCT_ONLY = "net_profit_product_only"
    #: items_revenue − discount − refunds, folded into the settlement currency.
    TURNOVER = "turnover"
    #: TURNOVER − COGS − non-shipping fees − allocated (FX-converted) overhead.
    PROFIT = "profit"


#: The only two a new settlement or config may use (rule 2). Legacy values stay
#: readable but unselectable; see the class docstring.
SELECTABLE_FORMULAS = frozenset(
    {PartnerSettlementFormula.TURNOVER, PartnerSettlementFormula.PROFIT}
)


class PartnerSettlement(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "partner_settlements"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shops.id", ondelete="RESTRICT"),
        nullable=False,
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: Creation-time snapshot of the partner's name, kept alongside `partner_id`
    #: for the same reason `percent` is kept: renaming a partner must not rewrite
    #: what an already-agreed settlement said. Identity queries use `partner_id`.
    partner_name: Mapped[str] = mapped_column(String(200), nullable=False)
    formula_type: Mapped[PartnerSettlementFormula] = mapped_column(
        Enum(
            PartnerSettlementFormula,
            name="partner_settlement_formula",
            values_callable=lambda enum: [m.value for m in enum],
            create_constraint=True,
        ),
        nullable=False,
    )
    percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    computed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    #: UAH per 1 USD, frozen at Calculate time — the same quantity, direction and
    #: precision as `orders.cogs_fx_rate`. NULL means NO CONVERSION WAS APPLIED
    #: (every base term was already in `base_currency`), never "rate unknown":
    #: a missing rate on a period that needed one is a 422, not a stored NULL.
    #: The staleness recompute replays with THIS rate, never the current one —
    #: otherwise every NBU move would falsely flag every unpaid settlement.
    fx_rate_used: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    payments = relationship(
        "PartnerPayment",
        back_populates="settlement",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "percent > 0 AND percent <= 100",
            name="ck_partner_settlements_percent_range",
        ),
        CheckConstraint(
            "period_end >= period_start",
            name="ck_partner_settlements_period_order",
        ),
        Index("ix_partner_settlements_shop_period", "shop_id", "period_start"),
        Index("ix_partner_settlements_partner_shop", "partner_name", "shop_id"),
        # PARTNER-CONFIG-1: serves the per-(shop, partner) overlap guard, which
        # runs on every settlement creation before any aggregate is computed.
        Index(
            "ix_partner_settlements_shop_partner_period",
            "shop_id",
            "partner_id",
            "period_start",
        ),
        Index("ix_partner_settlements_partner_id", "partner_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<PartnerSettlement {self.partner_name} "
            f"{self.computed_amount} {self.base_currency}>"
        )
