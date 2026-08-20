"""
OrderHub CRM — WesternBid Parcel Alert Model (WB-ALERTS-1)

The app's FIRST persistent notification mechanism. Nothing existing was
reusable: `Toast` is a 4-second per-session zustand store, and the two derived
dashboard banners (low-stock packaging, unallocated overhead) are recomputed on
every read with no row, no dismissal and no who/when.

One row per (parcel, kind) EPISODE. The foreign key targets
`wb_parcel.shipment_id`, NOT `wb_parcel_tracking.tracking_number`: UPS/USPS
parcels carry no Nova Poshta number, so they have no tracking row at all — and
`untracked_aging` exists precisely to name them.

Lifecycle — one concept covers dedupe, both closing paths and episode re-raise:

    "open"    == resolved_at IS NULL
    "visible" == open AND dismissed_at IS NULL

    raised ──(visible)──┬──────────── condition clears ──▶ resolved_at + resolution
                        └─ dismissed ──▶ hidden, STILL OPEN
                                         └─ condition clears ──▶ resolved

A dismissed alert stays OPEN, so the partial unique index below keeps the
generator from re-raising it while the condition persists. It closes only when
the condition actually disappears; a later recurrence then finds no open row and
inserts a NEW row — a new episode. `59500007135457` did exactly this in the
2026-08-20 review (dark → recovered → dark again).

`resolution` distinguishes the two auto-closing paths on purpose:

  * 'cleared'  — the parcel is still classified and the condition went away.
  * 'aged_out' — the parcel left the 60-day `classify_parcels` window, i.e. we
    stopped looking. For `untracked_aging` that is the ONLY non-manual exit, and
    calling it 'cleared' would be a lie: WesternBid's status vocabulary is
    creation-time only, so we can never learn that a UPS parcel was delivered.

No display columns. `tracking_number`, the carrier numbers and the recipient are
joined from `wb_parcel` at read time via the existing
`wb_tracking_service.extract_novapost_number` / `carrier_tracking_numbers` —
nothing to drift, and no second carrier-selection rule (the WB-TRACK-2 OQ1 trap).

`kind` / `resolution` are RAW STRINGS, not PG enums — the `Capability` and
`wb_parcel_tracking.stopped_reason` precedent.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class WbParcelAlert(Base):
    __tablename__ = "wb_parcel_alert"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "wb_parcel.shipment_id",
            ondelete="CASCADE",
            name="fk_wb_parcel_alert_shipment_id",
        ),
        nullable=False,
        index=True,
    )

    # delivery_problem | no_data_stuck | overdue_long | untracked_aging
    # (services/wb_tracking_service.py owns the vocabulary.)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)

    # Short Ukrainian reason shown on the dashboard row, refreshed on every poll
    # while the condition holds — so the number in it is as of the last
    # observation rather than as of the day the alert was raised.
    detail: Mapped[str] = mapped_column(Text, nullable=False)

    raised_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # The last poll at which the condition still held. Evidence for the
    # auto-resolve below: a row whose last_seen_at stops advancing is one the
    # generator is no longer finding.
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Manual close by OWNER/MANAGER — who and when (task rule 4). Kept on the
    # row after it later resolves, so the record reads "dismissed by X on D1,
    # condition cleared on D2".
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dismissed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_wb_parcel_alert_dismissed_by_id",
        ),
        nullable=True,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 'cleared' | 'aged_out'. Raw string, same reasoning as `kind`.
    resolution: Mapped[str | None] = mapped_column(String(16), nullable=True)

    __table_args__ = (
        # Task rule 3 — at most ONE open alert per (parcel, kind) — enforced by
        # the database rather than by the generator remembering to check.
        Index(
            "uq_wb_parcel_alert_open",
            "shipment_id",
            "kind",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<WbParcelAlert {self.kind} parcel={self.shipment_id} "
            f"resolved={self.resolution!r}>"
        )
