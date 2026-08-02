"""add FX provenance columns to orders (FX-CONVERSION)

Three nullable columns recording HOW `orders.computed_production_cost` was
derived, stamped once when the order ships and never touched again.

  cogs_fx_rate        UAH per 1 USD — NBU's published quote direction, so
                      computed_production_cost = cogs_basis_amount / cogs_fx_rate
                      for a UAH->USD conversion. Numeric(12,6) holds the published
                      4dp with room to spare. We deliberately store the quote as
                      published rather than a normalised UAH->USD multiplier: the
                      reciprocal (0.0224...) loses precision at fixed scale and
                      cannot be checked against bank.gov.ua by eye.
  cogs_basis_amount   the pre-conversion total, in cogs_basis_currency.
  cogs_basis_currency the material currency the basis is denominated in.

Why store the basis at all, when the rate is already here: a rate alone cannot
decompose a recipe that mixes material currencies, and the append-only ledger
cannot stand in — MaterialMovement.unit_cost_at_movement has no currency column,
and its rounded delta does not reproduce the cost anyway (the cost fold uses the
un-rounded quantity by design). The sprint is forward-only, so a booking that
cannot be explained after the fact can never be repaired either.

All three are NULL for every existing row, which reads correctly: no order in the
database has ever booked a computed cost (every populated recipe hits the
currency-mismatch path this sprint removes).

Purely additive. Downgrade drops all three cleanly.

Revision ID: d90b7c25e4a1
Revises: c4f1a83e6b27
Create Date: 2026-08-02 17:22:41.093855
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd90b7c25e4a1'
down_revision: Union[str, None] = 'c4f1a83e6b27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'orders',
        sa.Column('cogs_fx_rate', sa.Numeric(precision=12, scale=6), nullable=True),
    )
    op.add_column(
        'orders',
        sa.Column('cogs_basis_amount', sa.Numeric(precision=12, scale=4), nullable=True),
    )
    op.add_column(
        'orders',
        sa.Column('cogs_basis_currency', sa.String(length=3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('orders', 'cogs_basis_currency')
    op.drop_column('orders', 'cogs_basis_amount')
    op.drop_column('orders', 'cogs_fx_rate')
