"""
OrderHub CRM — Order Case Models (CASE-1)

A per-order case log for problem orders: a parcel came back, the customer left
a 1★ review, we promised a reship and are waiting on an address. Until now that
thread lived in Gmail and in people's heads, and no surface answered "what are
we resolving right now vs. what is waiting".

An order may carry SEVERAL cases — a return and, separately, a review — each
with its own status, its own deadline and its own note stream. That is the
whole reason this is a table rather than a `problem` flag on `orders`.

Not parcel tracking. Nothing here touches `wb_*`; a case is a human workflow
object, and the fact that some cases are *about* a parcel does not make them
one. The bridge between the two (a "create case from this alert" button) is
deliberately a later sprint.

`case_type` / `status` / `note.kind` are RAW STRINGS validated in the Pydantic
layer, NOT PG enum types — the `Capability` precedent (`models/user.py:21-41`:
"deliberately NOT a PG enum type, so adding a future capability needs zero
`ALTER TYPE` migration") and `wb_parcel_alert.kind`. `case_type` ships with
`other` precisely because the vocabulary is expected to grow; making each future
type an `ALTER TYPE` migration — with the PG16 same-transaction restriction that
`d7f3a1c85e92_partner_config_1.py` documents at length — buys nothing here. The
accepted cost: the database will not reject a bad value written outside the API.

Timestamps use `server_default=func.now()`, NOT `server_default="now()"`. The
plain-string form is a literal that Postgres evaluates ONCE at DDL time and
freezes: `order_status_history.changed_at` (`models/order.py:373`, emitted at
`541a6af5ae43_initial_migration.py:143`) is why every order audit row shares one
fake timestamp. This table is an audit trail; that bug would gut it.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OrderCaseType(str, enum.Enum):
    """What kind of problem this is. Drives dashboard filtering and, later,
    per-quarter stats ("how many returns did we have?")."""

    RETURN = "return"
    LOST_PARCEL = "lost_parcel"
    RESHIP = "reship"
    REVIEW = "review"
    ADDRESS_ISSUE = "address_issue"
    CLAIM = "claim"
    OTHER = "other"


class OrderCaseStatus(str, enum.Enum):
    """`waiting` means the ball is NOT in our court — customer reply, carrier,
    claim under review. There is deliberately no separate triage state: a case
    is created because someone already decided it matters."""

    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    RESOLVED = "resolved"


class OrderCaseNoteKind(str, enum.Enum):
    """`system` rows are written by the service on a status change, so the
    timeline reads as one stream rather than two merged at render time.

    A discriminator column rather than a prefix inside `text`: encoding
    structure in prose is what `DetailTimeline.humanizeComment()` already pays
    for, reverse-parsing "Fields updated: …" with a regex to recover the fields
    the writer knew and threw away.
    """

    COMMENT = "comment"
    SYSTEM = "system"


class OrderCase(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One open question about one order."""

    __tablename__ = "order_case"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE", name="fk_order_case_order_id"),
        nullable=False,
        index=True,
    )

    # OrderCaseType value. See the module docstring on why this is not a PG enum.
    case_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Short free-text headline — "Повернулась, клієнт хоче переслати".
    title: Mapped[str] = mapped_column(Text, nullable=False)

    # OrderCaseStatus value.
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=OrderCaseStatus.IN_PROGRESS.value,
        server_default=OrderCaseStatus.IN_PROGRESS.value,
    )

    # "What happens next" — shown on the dashboard row. The single most useful
    # field when someone else picks the case up mid-thread.
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Deadline / come-back-to-it date. A `waiting` case past this does NOT
    # auto-transition (task rule 4): it sorts first and renders red. No
    # scheduler is involved anywhere in this feature — the dashboard query is
    # the whole mechanism, which is what keeps it honest about "now".
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Who is on it. SET NULL rather than CASCADE: deleting a user must not
    # delete the record of a problem the business had.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_order_case_owner_id"),
        nullable=True,
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_order_case_created_by_id"),
        nullable=False,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Optional summary at close. Prompted for, never required — a forced field
    # gets filled with "ok".
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="cases")
    owner = relationship("User", foreign_keys=[owner_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    notes = relationship(
        "OrderCaseNote",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="OrderCaseNote.created_at, OrderCaseNote.id",
        lazy="selectin",
    )

    __table_args__ = (
        # The dashboard query: non-resolved cases, overdue first. Both columns
        # are in its WHERE/ORDER BY.
        Index("ix_order_case_status_due_at", "status", "due_at"),
    )

    def __repr__(self) -> str:
        return f"<OrderCase {self.case_type} [{self.status}] order={self.order_id}>"


class OrderCaseNote(Base, UUIDPrimaryKeyMixin):
    """Append-only entry on a case's timeline.

    No edit and no delete in v1 — same discipline as `order_status_history`,
    and for the same reason: the timeline IS the record. There are no update or
    delete routes, which `tests/test_order_cases.py` asserts against the live
    route table rather than trusting anyone to remember.
    """

    __tablename__ = "order_case_note"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("order_case.id", ondelete="CASCADE", name="fk_order_case_note_case_id"),
        nullable=False,
        index=True,
    )

    # OrderCaseNoteKind value. 'system' rows record status transitions.
    kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=OrderCaseNoteKind.COMMENT.value,
        server_default=OrderCaseNoteKind.COMMENT.value,
    )

    # RESTRICT, and NOT NULL even on system rows: task rule 3 requires status
    # transitions to be visible "with author + timestamp", so a system note
    # still names the human whose action produced it.
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_order_case_note_author_id"),
        nullable=False,
    )

    text: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    case = relationship("OrderCase", back_populates="notes")
    author = relationship("User")

    def __repr__(self) -> str:
        return f"<OrderCaseNote {self.kind} case={self.case_id}>"
