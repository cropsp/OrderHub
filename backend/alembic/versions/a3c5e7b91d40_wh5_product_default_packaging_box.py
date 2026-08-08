"""WH-5: the product's default packaging box.

`products.default_packaging_box_id` answers "which box does this product ship in".
DESIGN Q5 deferred it; the WH-5 retro-consumption runner needs it, because
historical orders carry `packaging_id` NULL almost everywhere — before WH-2 the
packaging picker was UA-gated, so an international order could not have one at all.

Product-level, not variant-level: variants of one product ship in the same box.

Nullable with no backfill and no default. There is no honest value to guess here —
a wrong default box would be consumed at SHIPPED and priced into COGS, and NULL is
already a fully supported state everywhere the column is read (both the live
consumption path and the runner treat "no box" as legal and silent). The catalogue
is populated by hand, per product, in runbook Phase 3.

ondelete=SET NULL mirrors `orders.packaging_id` and `orders.computed_packaging_box_id`.
Since WH-2 a box delete ARCHIVES rather than deletes (the geometry row survives so
the frozen ledger is not cascaded away), so this clause is a backstop that in
practice never fires.

The FK constraint is named explicitly, matching `fk_packaging_boxes_material_id` —
an unnamed constraint gets a server-generated name that autogenerate then wants to
"fix" on every subsequent run.

Downgrade drops the constraint and the column; the round trip loses only the
assignments themselves, which is the honest outcome for a column that has no other
home.

Revision ID: a3c5e7b91d40
Revises: f2a7c1d84b63
Create Date: 2026-08-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a3c5e7b91d40"
down_revision: Union[str, None] = "f2a7c1d84b63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FK_NAME = "fk_products_default_packaging_box_id"


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "default_packaging_box_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        FK_NAME,
        "products",
        "packaging_boxes",
        ["default_packaging_box_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(FK_NAME, "products", type_="foreignkey")
    op.drop_column("products", "default_packaging_box_id")
