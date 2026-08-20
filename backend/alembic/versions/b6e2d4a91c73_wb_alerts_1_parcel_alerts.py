"""add parcel alert table (WB-ALERTS-1)

One additive table, no backfill, nothing existing is touched:

  * `wb_parcel_alert` — one row per (parcel, kind) alert EPISODE, raised by the
    generator that now runs inside `wb_tracking_service.run_poll`.

Keyed on `wb_parcel.shipment_id` rather than
`wb_parcel_tracking.tracking_number`: UPS/USPS parcels have no Nova Poshta
number and therefore no tracking row, and the `untracked_aging` alert exists
precisely to name them.

The partial unique index is the point of this migration as much as the table
is — it enforces "at most one OPEN alert per (parcel, kind)" (task rule 3) in
the database, so a generator bug cannot quietly produce duplicates. "Open"
means `resolved_at IS NULL`, which a DISMISSED-but-unresolved row still
satisfies: that is how a dismissal keeps blocking a re-raise while the
condition persists, while a condition that clears and later recurs opens a
genuinely new row.

`kind` and `resolution` are raw text, not PG enums — the same reasoning as
`wb_parcel_tracking.stopped_reason`, and it sidesteps the PG16 same-transaction
enum restriction the PARTNER-CONFIG-1 migration documents.

Reversible: downgrade drops the index and the table.

Revision ID: b6e2d4a91c73
Revises: a3c5e7b91d40
Create Date: 2026-08-20 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6e2d4a91c73"
down_revision: Union[str, None] = "a3c5e7b91d40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_parcel_alert",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("shipment_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column(
            "raised_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_by_id", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(
            ["shipment_id"],
            ["wb_parcel.shipment_id"],
            name="fk_wb_parcel_alert_shipment_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dismissed_by_id"],
            ["users.id"],
            name="fk_wb_parcel_alert_dismissed_by_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wb_parcel_alert_shipment_id", "wb_parcel_alert", ["shipment_id"]
    )
    # Task rule 3, enforced by the DB. Partial on `resolved_at IS NULL` so a
    # closed episode never blocks the next one.
    op.create_index(
        "uq_wb_parcel_alert_open",
        "wb_parcel_alert",
        ["shipment_id", "kind"],
        unique=True,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_wb_parcel_alert_open", table_name="wb_parcel_alert")
    op.drop_index("ix_wb_parcel_alert_shipment_id", table_name="wb_parcel_alert")
    op.drop_table("wb_parcel_alert")
