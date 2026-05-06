"""add variant pricing and stock fields

Revision ID: 7aae7d72589d
Revises: eade98846155
Create Date: 2026-05-06 14:06:52.310360
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7aae7d72589d'
down_revision: Union[str, None] = 'eade98846155'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'product_variants',
        sa.Column('price', sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        'product_variants',
        sa.Column('cost_price', sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        'product_variants',
        sa.Column('stock_quantity', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('product_variants', 'stock_quantity')
    op.drop_column('product_variants', 'cost_price')
    op.drop_column('product_variants', 'price')
