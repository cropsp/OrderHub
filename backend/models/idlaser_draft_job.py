"""
OrderHub CRM — IdlaserDraftJob Model (S004-mcp-wrapper)

Tracks an ID-Laser draft-generation run: customer REFERENCE photo in,
DXF MOCKUP attachment out. The row itself is the audit trail (rule 11) —
who triggered, when, manual corners or not, result, errors. Multiple
rows per order are allowed (rule 16 / OQ-4): re-clicking Generate Draft
creates a new row; the latest READY job's result is just a regular
attachment in Production Assets.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IdlaserDraftJobState(str, enum.Enum):
    """State machine for IdlaserDraftJob (S004 master rule 2)."""

    PENDING = "pending"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IdlaserDraftJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "idlaser_draft_jobs"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SET NULL on both attachment FKs so operator-deletes of the photo or
    # the generated DXF leave the audit row intact (rule 26).
    photo_attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attachments.id", ondelete="SET NULL"),
        nullable=True,
    )
    result_attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("attachments.id", ondelete="SET NULL"),
        nullable=True,
    )
    triggered_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    state: Mapped[IdlaserDraftJobState] = mapped_column(
        Enum(
            IdlaserDraftJobState,
            name="idlaser_draft_job_state",
            values_callable=lambda enum_: [m.value for m in enum_],
            create_constraint=True,
        ),
        nullable=False,
        default=IdlaserDraftJobState.PENDING,
    )
    manual_corners: Mapped[list[list[float]] | None] = mapped_column(
        JSONB, nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    order = relationship("Order")
    triggered_by = relationship("User", foreign_keys=[triggered_by_id])
    photo_attachment = relationship(
        "Attachment", foreign_keys=[photo_attachment_id]
    )
    result_attachment = relationship(
        "Attachment", foreign_keys=[result_attachment_id]
    )

    __table_args__ = (
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL "
            "OR completed_at >= started_at",
            name="ck_idlaser_draft_jobs_completed_after_started",
        ),
        Index(
            "ix_idlaser_draft_jobs_order_state",
            "order_id",
            "state",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<IdlaserDraftJob {self.id} order={self.order_id} "
            f"state={self.state.value}>"
        )
