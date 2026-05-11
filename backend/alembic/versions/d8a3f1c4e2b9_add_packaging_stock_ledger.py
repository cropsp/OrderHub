"""add_packaging_stock_ledger

Revision ID: d8a3f1c4e2b9
Revises: f3e9c2a18b07
Create Date: 2026-05-11 12:00:00.000000

PKG-2: hybrid event-sourcing pattern for packaging stock counting.
- New table `packaging_stock_movements` (ledger of every stock change).
- New columns `stock_quantity` + `low_stock_threshold` on `packaging_boxes`
  (cached counter + per-box alert threshold). NOT NULL with constant
  defaults — metadata-only ADD COLUMN on Postgres >= 11.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8a3f1c4e2b9"
down_revision: Union[str, None] = "f3e9c2a18b07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "packaging_boxes",
        sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "packaging_boxes",
        sa.Column("low_stock_threshold", sa.Integer(), nullable=False, server_default="5"),
    )

    op.create_table(
        "packaging_stock_movements",
        sa.Column("box_id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=True),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column(
            "reason",
            sa.Enum(
                "initial_stock",
                "restock",
                "ttn_create",
                "ttn_delete",
                "adjustment",
                name="packaging_stock_movement_reason",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["box_id"], ["packaging_boxes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_packaging_stock_movements_box_id"),
        "packaging_stock_movements",
        ["box_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_packaging_stock_movements_order_id"),
        "packaging_stock_movements",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_packaging_stock_movements_created_at"),
        "packaging_stock_movements",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_packaging_stock_movements_created_at"),
        table_name="packaging_stock_movements",
    )
    op.drop_index(
        op.f("ix_packaging_stock_movements_order_id"),
        table_name="packaging_stock_movements",
    )
    op.drop_index(
        op.f("ix_packaging_stock_movements_box_id"),
        table_name="packaging_stock_movements",
    )
    op.drop_table("packaging_stock_movements")
    sa.Enum(name="packaging_stock_movement_reason").drop(op.get_bind(), checkfirst=False)

    op.drop_column("packaging_boxes", "low_stock_threshold")
    op.drop_column("packaging_boxes", "stock_quantity")
