"""drop shop_id from packaging_boxes — shared inventory model

WARNING — downgrade caveat
==========================
The downgrade re-adds shop_id as a NULLABLE column. The original shop
ownership of existing rows CANNOT be recovered without an external
snapshot. Manual SQL re-population is required after downgrade for the
system to function correctly under the old per-shop model (e.g., the
auto-fit engine's shop filter expects every row to have shop_id).

This is documented data loss, not a bug.

Revision ID: f3e9c2a18b07
Revises: c7f1a2b3d4e5
Create Date: 2026-05-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3e9c2a18b07"
down_revision: Union[str, None] = "c7f1a2b3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "packaging_boxes_shop_id_fkey",
        "packaging_boxes",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_packaging_boxes_shop_id",
        table_name="packaging_boxes",
    )
    op.drop_column("packaging_boxes", "shop_id")


def downgrade() -> None:
    # See module docstring for the data-loss warning. shop_id is re-added
    # NULLABLE; restoring NOT NULL + FK + CASCADE requires manual data
    # re-population first.
    op.add_column(
        "packaging_boxes",
        sa.Column("shop_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_packaging_boxes_shop_id",
        "packaging_boxes",
        ["shop_id"],
    )
    op.create_foreign_key(
        "packaging_boxes_shop_id_fkey",
        "packaging_boxes",
        "shops",
        ["shop_id"],
        ["id"],
        ondelete="CASCADE",
    )
