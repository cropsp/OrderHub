"""
OrderHub CRM — Partner Model (PARTNER-CONFIG-1)

The partner IDENTITY, global by design: the same person working with two shops is
one row here with one aggregate balance, not two free-text strings that a typo can
silently split (which is exactly what `partner_name` allowed before this sprint).

Deliberately thin — name, active flag, notes. Everything shop-specific (percent,
basis, settlement currency) lives in `shop_partner_config`, because those differ
per shop for the same person.

`partner_name` survives on `partner_settlements` / `partner_payments` as a
CREATION-TIME SNAPSHOT: renaming a partner here must not silently rewrite the
label on settlements that were already agreed and possibly already paid, for the
same reason `percent` and `formula_type` are snapshotted (see PartnerSettlement).
Read `partner_id` when you mean identity; read `partner_name` when you mean
"what this row said when it was created".
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from models.base import Base, UUIDPrimaryKeyMixin


class Partner(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "partners"

    #: Unique across the whole system — the constraint is what makes
    #: "one person, one balance" enforceable rather than aspirational.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Soft retirement. Never delete a partner who has settlements: both FKs are
    #: ondelete=RESTRICT, so the DB refuses, and history must stay readable.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    #: NULL for the rows the PARTNER-CONFIG-1 migration created by deduplicating
    #: historical `partner_name` values — nobody created those through the UI.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    __table_args__ = (UniqueConstraint("name", name="uq_partners_name"),)

    def __repr__(self) -> str:
        return f"<Partner {self.name}{'' if self.is_active else ' (inactive)'}>"
