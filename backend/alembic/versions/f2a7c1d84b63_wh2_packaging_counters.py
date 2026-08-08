"""WH-2: move the packaging counters onto the paired materials.

WH-1 paired every packaging box with a Material but deliberately left the counters
where they were, stale, with a note that WH-2 would carry them over once the
consumption trigger moved. It has: the box is consumed at SHIPPED through the
materials ledger, so `packaging_boxes.stock_quantity` and `low_stock_threshold`
now have no writer at all. Two counters for one physical object is a guaranteed
divergence, so this migration copies them across and drops the columns.

WHAT HAPPENS TO THE NUMBERS

`stock_quantity` is SUMMED onto the material, not assigned. In the expected case
the material still sits at WH-1's backfilled 0 and the sum is a plain copy. But
packaging materials have been visible in the materials UI since WH-1, so a receipt
recorded against one since then is real stock that a straight overwrite would
silently delete. Adding is right in both cases and destructive in neither. Any box
whose material was NOT at zero is logged by name — accuracy is not critical here
(§10.3 puts a physical count after the launch, not before), but a silent merge is.

`low_stock_threshold` is a setting, not a quantity, so it is COPIED — and only
where the material's is still 0, WH-1's backfill value. `PATCH /api/materials`
lets that field through freely (only name and category are refused), so anyone who
set one there has expressed an intent this migration must not overwrite.

`packaging_stock_movements` is NOT migrated and NOT touched. It is frozen as
read-only archaeology: its rows are quantity-only, carry no cost, and the counters
they sum to are exactly what is being copied above. Replaying them into
material_movements would fabricate a cost history that never existed.

DOWNGRADE IS LOSSY, AND SPECIFICALLY HOW

It restores the columns from the materials' CURRENT values, not from whatever the
boxes held when this ran. Anything the ledger did in between — consumption at
SHIPPED, receipts, adjustments — comes back folded into one number, and the
individual movements stay in material_movements where they belong. Fractional
stock rounds to an integer (the restored column is Integer, and PG's ROUND is
half-away-from-zero, so a box sitting at -1.5 comes back as -2).

The round trip is still exact, via the same carrier-table idiom WH-1 used
(`e9b2f4c7a318`): the downgrade parks what it handed back, and a subsequent
upgrade subtracts that amount before re-adding, so upgrade → downgrade → upgrade
never double-counts and never zeroes a material that has since earned real stock.
Zeroing the material on the way down was the obvious alternative and is wrong: it
would leave `materials.stock_quantity` permanently contradicting the movement rows
that produced it, for anyone who downgraded and stayed there.

On prod this upgrade is vacuous — `packaging_boxes` has zero rows until WH-3 seeds
the catalogue.

Revision ID: f2a7c1d84b63
Revises: e9b2f4c7a318
Create Date: 2026-08-08
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a7c1d84b63"
down_revision: Union[str, None] = "e9b2f4c7a318"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


logger = logging.getLogger("alembic.runtime.migration")

CARRIER_TABLE = "wh2_packaging_counter_carrier"

CARRIER_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {CARRIER_TABLE} (
    box_id             UUID PRIMARY KEY,
    material_id        UUID NOT NULL,
    restored_qty       NUMERIC(12, 2) NOT NULL,
    restored_threshold NUMERIC(12, 2) NOT NULL
)
"""

# The values the restored columns carried before WH-2, straight from
# d8a3f1c4e2b9_add_packaging_stock_ledger.py. Restating them is what makes a
# downgraded schema identical to the pre-WH-2 head rather than merely similar.
BOX_STOCK_SERVER_DEFAULT = "0"
BOX_THRESHOLD_SERVER_DEFAULT = "5"

# WH-1's backfill value. A threshold still sitting at it was never touched by an
# operator, so the box's value may take its place.
WH1_BACKFILLED_THRESHOLD = 0


def upgrade() -> None:
    bind = op.get_bind()

    carrier_exists = bind.execute(
        sa.text("SELECT to_regclass(:t) IS NOT NULL"), {"t": CARRIER_TABLE}
    ).scalar()

    # 1. Report any material that already carries stock of its OWN, so a merge is
    #    never silent. Runs before the UPDATE, while the two numbers are separable.
    #
    #    On a re-upgrade the material is holding what the downgrade handed back, so
    #    that amount is subtracted first — otherwise every box would be reported as
    #    a merge on the way back up, which is exactly the false alarm an operator
    #    reading this log cannot afford.
    if carrier_exists:
        probe = f"""
            SELECT m.name,
                   m.stock_quantity - COALESCE(k.restored_qty, 0) AS material_qty,
                   b.stock_quantity AS box_qty
            FROM packaging_boxes b
            JOIN materials m ON m.id = b.material_id
            LEFT JOIN {CARRIER_TABLE} k ON k.box_id = b.id
            WHERE m.stock_quantity - COALESCE(k.restored_qty, 0) <> 0
        """
    else:
        probe = """
            SELECT m.name, m.stock_quantity AS material_qty, b.stock_quantity AS box_qty
            FROM packaging_boxes b
            JOIN materials m ON m.id = b.material_id
            WHERE m.stock_quantity <> 0
        """

    for row in bind.execute(sa.text(probe)).fetchall():
        logger.warning(
            "WH-2: «%s» had %s units on its material and %s on its box; "
            "the counters were added together (%s).",
            row.name,
            row.material_qty,
            row.box_qty,
            row.material_qty + row.box_qty,
        )

    # 2. Carry the counters over. COALESCE against the carrier so an
    #    upgrade → downgrade → upgrade cycle subtracts whatever the downgrade
    #    already handed back; on a virgin DB the carrier is absent and this
    #    degenerates to a plain sum.
    if carrier_exists:
        op.execute(
            f"""
            UPDATE materials m
            SET stock_quantity = m.stock_quantity
                                 + b.stock_quantity
                                 - COALESCE(k.restored_qty, 0)
            FROM packaging_boxes b
            LEFT JOIN {CARRIER_TABLE} k ON k.box_id = b.id
            WHERE b.material_id = m.id
            """
        )
    else:
        op.execute(
            """
            UPDATE materials m
            SET stock_quantity = m.stock_quantity + b.stock_quantity
            FROM packaging_boxes b
            WHERE b.material_id = m.id
            """
        )

    op.execute(
        f"""
        UPDATE materials m
        SET low_stock_threshold = b.low_stock_threshold
        FROM packaging_boxes b
        WHERE b.material_id = m.id
          AND m.low_stock_threshold = {WH1_BACKFILLED_THRESHOLD}
        """
    )

    # 3. Drop the columns. Nothing writes them any more: the TTN hooks, the restock
    #    endpoint and the initial_quantity path were all removed in this sprint.
    op.drop_column("packaging_boxes", "stock_quantity")
    op.drop_column("packaging_boxes", "low_stock_threshold")

    op.execute(f"DROP TABLE IF EXISTS {CARRIER_TABLE}")

    moved = bind.execute(
        sa.text("SELECT count(*) FROM packaging_boxes")
    ).scalar()
    logger.info(
        "WH-2: counters for %s packaging box(es) now live on their materials; "
        "packaging_boxes.stock_quantity / low_stock_threshold dropped.",
        moved,
    )


def downgrade() -> None:
    op.add_column(
        "packaging_boxes",
        sa.Column(
            "stock_quantity",
            sa.Integer(),
            nullable=False,
            server_default=BOX_STOCK_SERVER_DEFAULT,
        ),
    )
    op.add_column(
        "packaging_boxes",
        sa.Column(
            "low_stock_threshold",
            sa.Integer(),
            nullable=False,
            server_default=BOX_THRESHOLD_SERVER_DEFAULT,
        ),
    )

    # Hand the current material values back to the boxes. ROUND, not TRUNC: a
    # counter of 3.5 belongs closer to 4 than to 3, and negative stock is a legal
    # state that must survive the trip rather than being clamped to zero.
    op.execute(
        """
        UPDATE packaging_boxes b
        SET stock_quantity = ROUND(m.stock_quantity)::int,
            low_stock_threshold = ROUND(m.low_stock_threshold)::int
        FROM materials m
        WHERE m.id = b.material_id
        """
    )

    # Park what was handed back so a re-upgrade can subtract it. The materials keep
    # their counters: zeroing them here would contradict material_movements for as
    # long as anyone stayed on the downgraded revision.
    op.execute(CARRIER_TABLE_DDL)
    op.execute(
        f"""
        INSERT INTO {CARRIER_TABLE} (box_id, material_id, restored_qty, restored_threshold)
        SELECT b.id, m.id, m.stock_quantity, m.low_stock_threshold
        FROM packaging_boxes b
        JOIN materials m ON m.id = b.material_id
        ON CONFLICT (box_id) DO UPDATE
        SET restored_qty = EXCLUDED.restored_qty,
            restored_threshold = EXCLUDED.restored_threshold
        """
    )

    parked = op.get_bind().execute(
        sa.text(f"SELECT count(*) FROM {CARRIER_TABLE}")
    ).scalar()
    logger.warning(
        "WH-2 downgrade: restored packaging counters for %s box(es) from their "
        "materials' CURRENT values (not the historical ones), rounded to whole "
        "units. The materials keep their counters; %s carrier row(s) let a "
        "re-upgrade avoid double-counting.",
        parked,
        parked,
    )
