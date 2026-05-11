"""add packaging_id to orders

Revision ID: c7f1a2b3d4e5
Revises: 7aae7d72589d
Create Date: 2026-05-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7f1a2b3d4e5"
down_revision: Union[str, None] = "7aae7d72589d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("packaging_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_orders_packaging_id",
        "orders",
        ["packaging_id"],
    )
    op.create_foreign_key(
        "fk_orders_packaging_id",
        "orders",
        "packaging_boxes",
        ["packaging_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_orders_packaging_id", "orders", type_="foreignkey")
    op.drop_index("ix_orders_packaging_id", table_name="orders")
    op.drop_column("orders", "packaging_id")
