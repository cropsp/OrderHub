"""add_bom_and_order_computed_cost

Revision ID: f4d8b3a25c91
Revises: e1c4d92a87bf
Create Date: 2026-05-14 14:00:00.000000

MAT-3: BomItem entity (recipe rows linking Product → Material) plus the
forward-compat `orders.computed_production_cost` column.

Creates one table:
  - bom_items                  (Product × Material recipe lines)

Adds one column:
  - orders.computed_production_cost (nullable Numeric(10,2); populated by
                                     MAT-4's consumption hook, NOT by MAT-3)

The CHECK constraint `ck_bom_items_qty_positive` enforces qty_per_unit > 0 at
DB level (model-level gt=0 doesn't protect against direct SQL). The unique
constraint `uq_bom_items_product_material` blocks duplicate (product, material)
rows — operators sum quantities into one row instead of authoring two lines.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4d8b3a25c91"
down_revision: Union[str, None] = "e1c4d92a87bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bom_items",
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("material_id", sa.UUID(), nullable=False),
        sa.Column("qty_per_unit", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id", "material_id", name="uq_bom_items_product_material"
        ),
        sa.CheckConstraint("qty_per_unit > 0", name="ck_bom_items_qty_positive"),
    )
    op.create_index(
        op.f("ix_bom_items_product_id"),
        "bom_items",
        ["product_id"],
        unique=False,
    )

    op.add_column(
        "orders",
        sa.Column(
            "computed_production_cost",
            sa.Numeric(precision=10, scale=2),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "computed_production_cost")

    op.drop_index(op.f("ix_bom_items_product_id"), table_name="bom_items")
    op.drop_table("bom_items")
