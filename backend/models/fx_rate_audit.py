"""
OrderHub CRM — FX Rate Audit (FX-CONVERSION)

Append-only record of every change to the UAH/USD rate configuration. One row per
mutation, whether it came from the OWNER (manual override set/cleared, source URL
edited) or from the nightly NBU refresh.

Why this exists: the rate silently re-prices every SUBSEQUENT shipment, globally,
and the sprint is forward-only — already-booked orders never move. So when a bad
rate is discovered after the fact, this table is the only thing that answers
"which window was booked at it". `app_settings.updated_by_id` records the last
writer and nothing else — no old value, no history.

Mirrors models/access_audit.py: one table, string-typed object/action columns, and
SYSTEM_USER_ID (constants.py) as the actor for automated writes. Written
flush-only; the router / scheduler job owns the commit.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, UUIDPrimaryKeyMixin


class FxRateAudit(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "fx_rate_audit"

    # Who changed it (a user id, or SYSTEM_USER_ID for the scheduled NBU refresh).
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Which app_settings key changed (fx_uah_per_usd_override, fx_source_url, ...).
    setting_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # Values as stored (plaintext). NULL old_value = the key was previously unset;
    # NULL new_value = the key was cleared (the row is deleted, see the router).
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provenance: "manual" (owner set it) | "nbu" (scheduled refresh) | "clear"
    # (owner cleared the override, reverting to auto).
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<FxRateAudit actor={self.actor_id} {self.setting_key}: "
            f"{self.old_value} -> {self.new_value} src={self.source}>"
        )
