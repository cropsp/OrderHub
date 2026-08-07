"""
OrderHub CRM — ShopPartnerConfig Model (PARTNER-CONFIG-1)

What one partner is owed on one shop: the percent, the basis, and the currency
the settlement is denominated in. Several partners per shop, each independent;
the same partner on two shops carries two config rows and one identity.

Before this sprint the percent was typed per settlement and the basis picked from
a dropdown every time. This table makes both configuration, and a settlement then
SNAPSHOTS whatever was in force (and may override it — rule 9), so changing a rate
here never moves a settlement that already exists.

`basis` reuses the EXISTING `partner_settlement_formula` PG enum rather than
minting a second type — a config's basis and a settlement's formula_type are the
same concept, and one type means a settlement can be compared to its config
without a cast. Only TURNOVER and PROFIT are selectable; the two legacy values
remain in the type so old settlements keep deserialising. That restriction is
enforced in `schemas/partner_payout.py`, NOT by a CHECK constraint — see the
migration docstring for why a CHECK naming a freshly-added enum value cannot
exist in the migration that adds it.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from models.base import Base, UUIDPrimaryKeyMixin
from models.partner_settlement import PartnerSettlementFormula


class ShopPartnerConfig(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "shop_partner_config"

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
    percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    basis: Mapped[PartnerSettlementFormula] = mapped_column(
        Enum(
            PartnerSettlementFormula,
            name="partner_settlement_formula",
            values_callable=lambda enum: [m.value for m in enum],
            create_constraint=True,
        ),
        nullable=False,
    )
    #: The currency every base term is folded into at Calculate time. Any term
    #: not in this currency converts via fx_service; no usable rate is a loud 422.
    settlement_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    #: Soft retirement — a partner who stopped working on this shop keeps his
    #: settlement history and his balance, but no longer appears as a default.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "percent > 0 AND percent <= 100",
            name="ck_shop_partner_config_percent_range",
        ),
        UniqueConstraint(
            "shop_id", "partner_id", name="uq_shop_partner_config_shop_partner"
        ),
        Index("ix_shop_partner_config_shop", "shop_id"),
        Index("ix_shop_partner_config_partner", "partner_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ShopPartnerConfig shop={self.shop_id} partner={self.partner_id} "
            f"{self.percent}% {self.basis.value} {self.settlement_currency}>"
        )
