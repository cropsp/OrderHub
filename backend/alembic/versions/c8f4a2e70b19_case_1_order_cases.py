"""order cases + append-only note timeline (CASE-1)

Two additive tables, no backfill, nothing existing is touched:

  * `order_case`      — one open question about one order. Several per order is
                        the normal case (a return AND, separately, a review).
  * `order_case_note` — append-only timeline entry. `kind` distinguishes a
                        human comment from a status-transition record written
                        by the service.

NO PG ENUM TYPES. `case_type`, `status` and `kind` are plain `String` columns
validated in the Pydantic layer — the `Capability` precedent
(`models/user.py:21-41`) and `wb_parcel_alert.kind`. `case_type` ships with
`other` and is expected to grow; a PG enum would make every future value an
`ALTER TYPE` migration subject to the PG16 same-transaction restriction that
`d7f3a1c85e92_partner_config_1.py` documents. A pleasant consequence: this
migration's downgrade is a plain drop, so the round-trip is clean by
construction and needs none of the explicit `sa.Enum(name=...).drop()`
bookkeeping that `a7c8e91d2b4f_add_idlaser_draft_jobs.py:88-92` has to do.

Timestamp defaults are `sa.text("now()")`, NOT the bare string `"now()"`. The
latter emits a LITERAL that Postgres freezes at DDL time —
`541a6af5ae43_initial_migration.py:143` is why every `order_status_history` row
carries the same fake `changed_at`. These tables are an audit trail; that bug
would gut them.

FK stances, each deliberate:
  * order_id   CASCADE  — deleting an order deletes its cases.
  * case_id    CASCADE  — deleting a case deletes its timeline.
  * owner_id   SET NULL — deleting a user must not delete the record of a
                          problem the business had.
  * created_by_id / author_id RESTRICT — authorship is the point of an audit
                          row, so a user with history cannot be hard-deleted.

Revision ID: c8f4a2e70b19
Revises: b6e2d4a91c73
Create Date: 2026-08-26 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8f4a2e70b19"
down_revision: Union[str, None] = "b6e2d4a91c73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_case",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("case_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="in_progress",
            nullable=False,
        ),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"],
            name="fk_order_case_order_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"],
            name="fk_order_case_owner_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"],
            name="fk_order_case_created_by_id", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_case_order_id", "order_case", ["order_id"])
    # The dashboard query — non-resolved cases, overdue first. Both columns are
    # in its WHERE / ORDER BY.
    op.create_index(
        "ix_order_case_status_due_at", "order_case", ["status", "due_at"]
    )

    op.create_table(
        "order_case_note",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind", sa.String(length=16), server_default="comment", nullable=False
        ),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["order_case.id"],
            name="fk_order_case_note_case_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"],
            name="fk_order_case_note_author_id", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_case_note_case_id", "order_case_note", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_order_case_note_case_id", table_name="order_case_note")
    op.drop_table("order_case_note")
    op.drop_index("ix_order_case_status_due_at", table_name="order_case")
    op.drop_index("ix_order_case_order_id", table_name="order_case")
    op.drop_table("order_case")
