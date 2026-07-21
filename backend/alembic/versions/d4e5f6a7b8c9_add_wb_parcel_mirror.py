"""add wb_parcel mirror table (WB-1)

Read-side mirror of WesternBid sent parcels. The poller upserts one row per WB
shipment keyed by `shipment_id` (WB's `Id`). `order_id` + `label_attachment_id`
are created now but stay unpopulated — WB-2 (matching) and WB-3 (labels) use them
so they need no second migration.

Status columns are raw text (WB's value sets are undocumented — the point of the
2-week recon window); list/blob columns are JSONB (the repo uses no ARRAY type).

Reversible: downgrade drops the table. No data backfill.

Revision ID: d4e5f6a7b8c9
Revises: a2b3c4d5e6f7
Create Date: 2026-07-21 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_parcel",
        sa.Column("shipment_id", sa.UUID(), nullable=False),
        sa.Column("shipping_type", sa.String(length=64), nullable=True),
        sa.Column("carrier_type", sa.String(length=64), nullable=True),
        sa.Column("shipping_service_type", sa.String(length=64), nullable=True),
        sa.Column(
            "tracking_numbers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("recipient_name", sa.String(length=255), nullable=True),
        sa.Column("recipient_postal_code", sa.String(length=32), nullable=True),
        sa.Column("recipient_country_code", sa.String(length=2), nullable=True),
        sa.Column("package", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("payment_status", sa.Text(), nullable=True),
        sa.Column("wb_status", sa.Text(), nullable=True),
        sa.Column("wb_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
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
        sa.Column("order_id", sa.UUID(), nullable=True),
        sa.Column("label_attachment_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["label_attachment_id"], ["attachments.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("shipment_id"),
    )
    op.create_index(
        "ix_wb_parcel_last_seen_at", "wb_parcel", ["last_seen_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_wb_parcel_last_seen_at", table_name="wb_parcel")
    op.drop_table("wb_parcel")
