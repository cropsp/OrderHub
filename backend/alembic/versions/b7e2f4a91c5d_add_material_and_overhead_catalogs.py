"""add_material_and_overhead_catalogs

Revision ID: b7e2f4a91c5d
Revises: d8a3f1c4e2b9
Create Date: 2026-05-14 00:00:00.000000

MAT-1: Materials warehouse foundation — catalog-only.
Two parallel tables (`materials`, `overhead_materials`) with no FK dependencies.
Stock/receipt/BOM scaffolding lands in MAT-2/MAT-3 in separate migrations.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e2f4a91c5d"
down_revision: Union[str, None] = "d8a3f1c4e2b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "materials",
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
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "current_unit_cost",
            sa.Numeric(precision=12, scale=4),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "stock_quantity",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "low_stock_threshold",
            sa.Numeric(precision=12, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "waste_percent",
            sa.Numeric(precision=5, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column("supplier_name", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_materials_is_active_name",
        "materials",
        ["is_active", "name"],
    )

    op.create_table(
        "overhead_materials",
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
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_overhead_materials_is_active_name",
        "overhead_materials",
        ["is_active", "name"],
    )


def downgrade() -> None:
    op.drop_index("ix_overhead_materials_is_active_name", table_name="overhead_materials")
    op.drop_table("overhead_materials")
    op.drop_index("ix_materials_is_active_name", table_name="materials")
    op.drop_table("materials")
