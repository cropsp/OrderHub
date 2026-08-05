"""add shipping/discount/tax breakdown to orders (ORDER-SHIPPING-1)

Three nullable columns decomposing what the customer actually paid, captured from
the channel at import instead of being reconstructed as a residual.

  shipping_revenue  what the customer was charged for shipping. Distinct from
                    `shipping_np_cost`, which is what WE pay Nova Poshta — this is
                    the revenue side of the same parcel.
  discount_total    stored POSITIVE, the sign Shopify reports it in
                    (`totalDiscountsSet`). The subtraction happens at render time;
                    a stored negative would have every consumer guessing the
                    convention.
  tax_total         tax collected from the customer, already inside `total_price`.

Numeric(10,2) — the same shape as every other money column on `orders`
(total_price, production_cost, shipping_np_cost, platform_fee).

NULL means UNKNOWN, and that distinction is load-bearing. Etsy CSV and manual
orders carry no such figures, and a `0.00` written where the truth is unknown is
the same class of defect as the residual this sprint removes: it reads as "this
order shipped free" when it means "nobody ever told us". The frontend renders a
NULL row as a clearly-labelled derived estimate, never as a fact.

Every existing row is NULL, so this migration alone changes no behaviour. Shopify
orders are populated going forward by the sync + webhook mappers, and
retroactively by the OWNER-only dry-run backfill at
POST /api/shops/{shop_id}/backfill-shipping — the order sync dedups on
(external_id, shop_id) and never revisits an existing row, which is why a separate
path is needed at all.

Purely additive. Downgrade drops all three cleanly.

Revision ID: a7c2e9f14b83
Revises: f2b8d6c40a15
Create Date: 2026-08-05 11:42:18.507341
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c2e9f14b83'
down_revision: Union[str, None] = 'f2b8d6c40a15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'orders',
        sa.Column('shipping_revenue', sa.Numeric(precision=10, scale=2), nullable=True),
    )
    op.add_column(
        'orders',
        sa.Column('discount_total', sa.Numeric(precision=10, scale=2), nullable=True),
    )
    op.add_column(
        'orders',
        sa.Column('tax_total', sa.Numeric(precision=10, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('orders', 'tax_total')
    op.drop_column('orders', 'discount_total')
    op.drop_column('orders', 'shipping_revenue')
