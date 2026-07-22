"""Add orders.order_number (Shopify human order name)

ORDER-CARD-1 Part 1. `orders.external_id` holds the numeric Shopify order id
(e.g. 1234567890); the human order name (e.g. 91890_1816) is fetched by the sync
(ORDERS_QUERY `name`) but was only ever used as a fallback title, never stored.
This adds a dedicated nullable column so the order card can show the number the
manager cross-references against Shopify / WesternBid. Nullable — Etsy and manual
orders have no Shopify name; existing Shopify rows are filled by the
`POST /api/shops/{shop_id}/backfill-order-numbers` admin pass.

Revision ID: c3d5e7f9a1b2
Revises: e7f8a9b0c1d2
Create Date: 2026-07-22 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3d5e7f9a1b2'
down_revision: Union[str, None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("order_number", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "order_number")
