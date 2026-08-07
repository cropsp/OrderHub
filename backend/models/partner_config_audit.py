"""
OrderHub CRM — Partner Config Audit (PARTNER-CONFIG-1)

Persistent record of every change to a partner's per-shop money configuration:
who changed the percent, the basis or the settlement currency, on which shop, and
what the values were before.

Why a dedicated table rather than reusing `access_audit`: that table's
`target_user_id` column means "whose access changed", and every query over it
("all access changes for user X" — its own docstring) reads it as a user id. A
partner is not a user. Putting a partner id there would make those queries
silently wrong, which is a worse outcome than one more small table.

Same conventions as `access_audit`: one row per change, `SYSTEM_USER_ID` as the
actor for any automated write, written flush-only from the router which owns the
commit. Append-only — never updated, never deleted.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, UUIDPrimaryKeyMixin


class PartnerConfigAudit(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "partner_config_audit"

    #: The user who made the change (or SYSTEM_USER_ID for automated writes).
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    #: "create" | "update" | "delete".
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Human-readable before→after, e.g. "percent 25.00→30.00, basis profit→turnover".
    #: Free text on purpose: this is read by a human reconstructing what was
    #: agreed, not queried by a machine.
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<PartnerConfigAudit {self.action} partner={self.partner_id} "
            f"shop={self.shop_id} by={self.actor_id}>"
        )
