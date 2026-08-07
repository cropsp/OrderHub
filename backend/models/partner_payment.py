"""
OrderHub CRM — PartnerPayment Model (PART-1)

Tracks actual money movements out to partners. Separate from settlements
because: (a) a single settlement may be paid in multiple installments;
(b) a payment can be standalone (advance, cross-period). settlement_id is
NULLABLE with ondelete=SET NULL — deleting a settlement leaves payments
intact (operator may re-link or leave unlinked).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
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


class PartnerPayment(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "partner_payments"

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
    #: Creation-time snapshot; identity queries use `partner_id`. See Partner.
    partner_name: Mapped[str] = mapped_column(String(200), nullable=False)
    settlement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partner_settlements.id", ondelete="SET NULL"),
        nullable=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    paid_at: Mapped[date] = mapped_column(Date, nullable=False)
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

    settlement = relationship("PartnerSettlement", back_populates="payments")

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_partner_payments_amount_positive"),
        Index("ix_partner_payments_shop_paid_at", "shop_id", "paid_at"),
        Index("ix_partner_payments_partner_shop", "partner_name", "shop_id"),
        Index("ix_partner_payments_settlement", "settlement_id"),
        Index("ix_partner_payments_partner_id", "partner_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<PartnerPayment {self.partner_name} "
            f"{self.amount} {self.currency} @ {self.paid_at}>"
        )
