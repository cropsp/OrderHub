"""
OrderHub CRM — Nova Poshta Delivery Tracking Models (WB-TRACK-1)

Two tables, deliberately NOT an extension of `wb_parcel` (task rule 1):
`wb_parcel` mirrors WesternBid's *creation-time* view and is refreshed only
inside a 3-day window, so its rows stop being updated exactly when the
interesting part of a parcel's life begins. Tracking has a different key
(the carrier's number, not WB's shipment id), a different cadence (daily) and a
different source (Nova Poshta's public endpoint).

`WbParcelTracking` holds the current state, one row per tracked number.
`WbTrackingEvent` holds one row per OBSERVED TRANSITION (task rule 2) — the
per-parcel log that answers "how long has this been sitting" without trusting
NP's own `TrackingUpdateDate`.

The primary key is `tracking_number`, NOT `shipment_id`: a parcel re-issued
under a new NP number keeps its old log intact, and both rows point at the same
shipment.

`status_code` / `status_text` are RAW TEXT with no Python enum (task rule 3).
This is not caution for its own sake — the codes we actually observe include
80, 115 and 121, and **none of the three appears in any published Nova Poshta
status list**. See services/wb_tracking_service.py for what is OBSERVED versus
merely DOCUMENTED.

All NP timestamps arrive as Europe/Kiev wall-clock with no offset and are
normalised to UTC on write — see services/np_tracking.py:parse_np_datetime.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class WbParcelTracking(Base):
    __tablename__ = "wb_parcel_tracking"

    # The carrier's own number (`5950…` for Nova Poshta Global). See
    # wb_tracking_service.extract_novapost_number for the selection rule.
    tracking_number: Mapped[str] = mapped_column(String(32), primary_key=True)

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wb_parcel.shipment_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # From `wb_parcel.shipping_type`, NOT from the tracking element's
    # `Identifier` (task rule 6). Identifier is a label, not the carrier: the one
    # USPS/ConsolidationOptimum number in prod is filed under Identifier "UPS",
    # while shipping_type tells the two apart.
    carrier: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Raw, verbatim, never enum-compared (task rule 3).
    status_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    np_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NP's own `TrackingUpdateDate` — when the carrier last scanned the parcel.
    np_last_movement_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NP's own delivery commitment. The "overdue" signal leads on this because it
    # is their promise, not our guess (task rule 4).
    np_scheduled_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # From `RecipientDateTime`. NOT from `ActualDeliveryDate`, which is empty on
    # every keyless response we have ever seen.
    np_delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # The keyless endpoint masks recipient identity — `RecipientFullName` and
    # `RecipientAddress` come back present-but-empty. City is all NP gives us;
    # a name has to come from `wb_parcel.recipient_name`.
    city_recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    international_delivery_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )

    # Stored because it costs nothing and a keyed future may populate it. NO
    # LOGIC MAY READ IT: on the keyless endpoint it is `[]` on every delivered
    # record and `''` on the one failed-delivery record we have — it has never
    # carried a reason. Failure and return are detected from status_code alone.
    undelivery_reasons: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Set when NP starts returning a stub payload for a number that previously
    # resolved (StatusCode 80 today — undocumented, see the service module).
    # `status_code` / `status_text` keep the last RESOLVED values while this is
    # set, so the operator still sees where the parcel was last seen.
    no_data_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    first_polled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_polled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # When we last observed a CHANGE, as opposed to merely polling.
    last_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Terminal condition — a stopped row is never polled again.
    polling_stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 'delivered' | 'aged_out'. Raw string, same reasoning as the status columns.
    stopped_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<WbParcelTracking {self.tracking_number} "
            f"code={self.status_code!r} stopped={self.stopped_reason!r}>"
        )


class WbTrackingEvent(Base):
    """One row per OBSERVED status transition (task rule 2).

    Not a snapshot log: re-polling an unchanged parcel writes nothing. A row is
    written when `(status_code, status_text)` differs from what we last stored —
    the TEXT participates because it carries the city ("Відправлення прямує до
    Phoenix"), so a same-code city change is a real movement.
    """

    __tablename__ = "wb_tracking_event"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tracking_number: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("wb_parcel_tracking.tracking_number", ondelete="CASCADE"),
        nullable=False,
    )

    status_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # NP's own timestamp for this state, when it gave us one.
    np_tracking_update_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When WE saw it. The reason this table exists: if NP's own
    # `TrackingUpdateDate` ever proves unreliable, this column still answers
    # "how long has this parcel been sitting".
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_wb_tracking_event_number_observed",
            "tracking_number",
            text("observed_at DESC"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<WbTrackingEvent {self.tracking_number} code={self.status_code!r} "
            f"observed={self.observed_at}>"
        )
