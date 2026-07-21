"""
OrderHub CRM — WesternBid Parcel Mirror Model (WB-1)

A local mirror of parcels WesternBid (WB) reports via
`GET /api/v1/Shipping/parcels/sent`. WB-1 builds only the read side: the poller
(`scheduler.run_westernbid_poll`) upserts one row per WB shipment, keyed by
`shipment_id` (WB's `Id`). Matching to a local order (WB-2) and label fetching
(WB-3) are separate sprints — `order_id` and `label_attachment_id` are added now
so those sprints need no second migration, but they stay unpopulated here.

`payment_status` / `wb_status` are stored as RAW TEXT on purpose (task rule 4):
WB does not document their value sets, so no Python enum, no mapping, no
comparison against `"Paid"`. The 2-week recon window learns the real values.
`tracking_numbers` and `package` are JSONB, following the codebase's list/blob
precedent (`models/idlaser_draft_job.py:78-80`) — the repo uses no `ARRAY` columns.
`wb_created_at` is normalized to UTC on write (task rule 8).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class WbParcel(Base):
    __tablename__ = "wb_parcel"

    # WB's `Id` (a uuid) is the natural key — upsert target (task rule 10).
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )

    # Raw classification strings mirrored verbatim (task rule 4 spirit — no enums).
    shipping_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    carrier_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shipping_service_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    # WB returns an array of tracking numbers → JSONB (no ARRAY precedent in repo).
    tracking_numbers: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_postal_code: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    recipient_country_code: Mapped[str | None] = mapped_column(
        String(2), nullable=True
    )

    # Opaque nested object from WB — kept whole for WB-2/WB-3 to mine later.
    package: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Undocumented value sets — RAW TEXT, never enum-compared (task rule 4).
    payment_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    wb_status: Mapped[str | None] = mapped_column(Text, nullable=True)

    # WB `CreatedDate` arrives with a non-UTC offset; normalized to UTC on write.
    wb_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # WB-2 / WB-3 wiring — created now, deliberately unpopulated this sprint.
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    label_attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attachments.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<WbParcel {self.shipment_id} status={self.wb_status!r} "
            f"payment={self.payment_status!r}>"
        )
