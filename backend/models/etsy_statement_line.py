"""
OrderHub CRM — Etsy statement line (STATEMENT-IMPORT)

One row of an Etsy payment-account statement, stored verbatim with its SIGNED
amount and a classification bucket.

Why store the raw lines rather than writing a fee straight onto the order:
statements overlap. A July statement can carry a credit against a June order, so
`order.platform_fee` must be an aggregate that can be RECOMPUTED from every line
accumulated so far, never a blind write. `services/etsy_statement_service.py`
owns that derivation.

Idempotency is `(shop_id, period_month)`: an import DELETEs the period and
re-inserts it whole. `row_index` (0-based position in the source file) makes each
physical row distinct, which is what preserves *legitimate* duplicates — Etsy
emits byte-identical rows that are genuinely separate charges (158 such copies
worth $14.00 across Jan–Jun 2026, mostly $0.04 auto-renew VAT and $0.20 listing
fees). A content hash would collapse them and under-book the fee. Replacing a
whole period also handles a re-issued statement correctly: rows that disappeared
are gone, which an upsert-only strategy can never achieve.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EtsyStatementLine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "etsy_statement_line"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: First day of the statement's calendar month — the import's natural key.
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    #: 0-based position in the source file. Part of the unique key so that
    #: byte-identical rows both survive.
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)

    #: The row's CHARGE date, which is what month attribution uses. Not the date
    #: quoted inside `info` — a Jan-1 row bills Dec-31 click-throughs.
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    info: Mapped[str] = mapped_column(Text, nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    #: Verbatim CSV columns, SIGNED. Credits are positive — never take abs().
    #: One exception: on `deposit` rows Etsy leaves every money column "--" and
    #: puts the payout in the title, so the parser lifts it into `amount_signed`
    #: to make the payout cross-check a plain SUM.
    amount_signed: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    fees_taxes_signed: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    #: `Amount + Fees & Taxes` on every observed row; the value the aggregates sum.
    net_signed: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    #: Classification from `services.etsy_statement_parser` (BUCKET_* constants).
    bucket: Mapped[str] = mapped_column(String(24), nullable=False)

    #: Etsy's own order number, as printed. Resolution to a local order is
    #: scoped to `shop_id` — cross-shop uniqueness is never assumed.
    order_external_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    #: Listing fees and auto-renew rows carry a LISTING id, not an order id.
    listing_external_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    #: NULL when the statement names an order this shop does not have — the row
    #: is still stored, counted and reported, never dropped and never guessed.
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    source_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    imported_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "period_month",
            "row_index",
            name="uq_etsy_statement_line_shop_period_row",
        ),
        Index(
            "ix_etsy_statement_line_shop_order_external",
            "shop_id",
            "order_external_id",
        ),
        Index("ix_etsy_statement_line_shop_period", "shop_id", "period_month"),
    )

    def __repr__(self) -> str:
        return (
            f"<EtsyStatementLine {self.entry_date} {self.entry_type} "
            f"{self.bucket} {self.net_signed}>"
        )
