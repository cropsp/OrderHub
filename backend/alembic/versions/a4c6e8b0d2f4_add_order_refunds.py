"""add order_refunds table (SHOPIFY-REFUNDS, Model 2)

Books Shopify refunds as separate, dated events. The order keeps its gross
`total_price`; each refund row carries its own `refunded_at` (the Shopify refund's
`createdAt`) so finance nets it out in the period the refund occurred, not the
order's original month.

`shopify_refund_id` is globally unique (Shopify refund ids are global) — the
idempotency key for the refund sync/upsert. `amount` is a positive magnitude;
finance subtracts it. Reversible: downgrade drops the table. No data backfill
(the retro-fix runs via the `/backfill-refunds` endpoint, gated by a dry-run).

Revision ID: a4c6e8b0d2f4
Revises: c3d5e7f9a1b2
Create Date: 2026-07-26 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4c6e8b0d2f4"
down_revision: Union[str, None] = "c3d5e7f9a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_refunds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("shopify_refund_id", sa.String(length=100), nullable=False),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shopify_refund_id", name="uq_order_refund_shopify_id"),
    )
    op.create_index("ix_order_refunds_order_id", "order_refunds", ["order_id"])
    op.create_index("ix_order_refunds_refunded_at", "order_refunds", ["refunded_at"])


def downgrade() -> None:
    op.drop_index("ix_order_refunds_refunded_at", table_name="order_refunds")
    op.drop_index("ix_order_refunds_order_id", table_name="order_refunds")
    op.drop_table("order_refunds")
