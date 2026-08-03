"""add fee_percent to shops (SHOP-FEE-1)

One nullable column holding a shop's TOTAL EFFECTIVE per-order transaction fee as
a percent — channel commission + payment gateway + merchant-of-record cut,
collapsed into a single number the operator calibrates against real net-received
figures. Applied to `orders.total_price` at order creation and frozen onto
`orders.platform_fee` there.

  fee_percent  Numeric(5,2), e.g. 8.00 = 8%. Same precision as
               materials.waste_percent — 2dp on a percent is +/-$0.005 on a $100
               order, and 999.99 of headroom is far past anything meaningful.

NULL means "not configured", which is deliberately distinct from 0.00 ("this shop
genuinely has no fee"). Every existing row is NULL, so this migration alone
changes no behaviour: a shop only starts accruing auto-computed fees once a rate
is entered. That preserves today's behaviour — `orders.platform_fee` is NULL on
every live order, so the P&L's fee term is 0 — until the operator opts in per shop.

The rate is intentionally NOT stored per order. A fee is computed once at order
creation from the shop's rate at that moment and frozen, mirroring
`orders.cogs_fx_rate`: changing the rate later must never silently re-price
closed months or already-settled partner payouts.

Purely additive. Downgrade drops the column cleanly.

Revision ID: e1a4c7b93d28
Revises: d90b7c25e4a1
Create Date: 2026-08-03 11:14:07.482913
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a4c7b93d28'
down_revision: Union[str, None] = 'd90b7c25e4a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'shops',
        sa.Column('fee_percent', sa.Numeric(precision=5, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('shops', 'fee_percent')
