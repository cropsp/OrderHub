"""add shipping_discount to orders (ORDER-SHIPPING-2)

A fourth nullable column completing the ORDER-SHIPPING-1 decomposition, and a
correction to what the third one means.

  shipping_discount  how much of the shipping charge was given away. Shopify
                     reports shipping twice — `shippingLines[].originalPriceSet`
                     (what the carrier rate came to) and `discountedPriceSet`
                     (what the customer was actually billed). The difference is
                     this column, stored POSITIVE like `discount_total`.

`discount_total` CHANGES MEANING with this migration: it is now the **item**
discount alone. It previously stored `totalDiscountsSet` verbatim, which folds
shipping promos in with item promos, so a free-shipping order booked its shipping
giveaway as if the customer had been discounted on the goods. Both derived values
had to move together — correcting shipping alone would have left the card's
identity (items - discount + shipping + tax = total) broken on exactly the orders
the bug affects. See the ORDER-SHIPPING-2 sprint notes.

Why a column rather than deriving it: the fact that a promo was given is worth
keeping, not just its effect. $103 of shipping was given away in 2026-07 alone
(orders 91890_1815 and 91890_1829, "Free Shipping over $199"); with three columns
that lands in the DB as an indistinguishable 0.00 shipping charge.

Numeric(10,2), matching every other money column on `orders`.

NULL means UNKNOWN, the same discipline the other three carry. Etsy CSV and
manual orders never report shipping lines. So do Shopify payloads that predate
this sprint — including rows the ORDER-SHIPPING-1 mappers already populated,
which have the other three set and this one unknown; the backfill targets those
rows specifically rather than skipping them for not being all-NULL.

Every existing row is NULL, so this migration alone changes no behaviour.

Purely additive. Downgrade drops it cleanly.

Revision ID: b8d3f0a25c47
Revises: a7c2e9f14b83
Create Date: 2026-08-05 12:41:03.882714

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d3f0a25c47'
down_revision: Union[str, None] = 'a7c2e9f14b83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'orders',
        sa.Column('shipping_discount', sa.Numeric(precision=10, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('orders', 'shipping_discount')
