"""WH-1: packaging boxes become materials — category, is_stock_tracked, material_id

Adds:
  - `materials.category` — 'MATERIAL' | 'PACKAGING'. A plain VARCHAR, NOT a PG enum
    (precedent: `user_capability.capability`), which sidesteps the PG16
    use-after-ADD-VALUE restriction documented in d7f3a1c85e92 for good;
  - `materials.is_stock_tracked` — false means the material contributes its cost to
    an order's COGS but moves no stock (service positions: cutting, sewing). Closes
    SVC-MATERIAL-NONSTOCK. Flipping it on the existing service materials is an
    operator action after deploy, not part of this migration;
  - `packaging_boxes.material_id` — NOT NULL UNIQUE FK, ondelete RESTRICT — plus a
    backfill that mints one Material per existing box.

Deliberately NOT here (WH-2): `packaging_boxes.stock_quantity` /
`low_stock_threshold` keep their counters, the TTN-create/delete decrement path in
routers/shipping.py is untouched, and the backfilled materials start at
stock_quantity 0. WH-2 copies the counters over when it moves the consumption
trigger to SHIPPED. The staleness is intentional; do not "fix" it here.

BACKFILL VALUES ARE FROZEN IN THIS FILE
───────────────────────────────────────
`_MATERIAL_DEFAULTS` restates unit/currency/cost/stock/flags literally rather than
importing services.catalog_service, so a later change to the application's defaults
cannot retroactively change what this historical migration did (the
c7d1e93b40af self-containment principle). Name collisions with existing materials
are accepted: `materials.name` is not unique, and the MCP dedup guards exist for
agent entry, not for migrations.

THE LINK TABLE, AND WHY IT SURVIVES A DOWNGRADE
───────────────────────────────────────────────
`wh1_packaging_material_link` is a carrier, not a backup. Nothing else can survive a
downgrade to re-identify a backfilled material: `packaging_boxes.material_id` is
dropped, `materials.category` is dropped, and names are not unique. Without the
carrier, `upgrade → downgrade → upgrade` would run clean but mint a SECOND material
for every box and orphan the first. So:

  * downgrade() writes one row per paired material — and one per material the
    operator has flagged `is_stock_tracked=false` or classified as PACKAGING — then
    leaves the table in place;
  * upgrade() consumes it: re-points each box at its original material, restores
    `category` / `is_stock_tracked` (both come back as the column server defaults
    otherwise), then drops the table.

On a virgin database the CREATE is a no-op and the restore UPDATEs match nothing.

DOWNGRADE DELETES NO MATERIALS — read before running it
───────────────────────────────────────────────────────
`material_receipts.material_id` and `material_movements.material_id` are both
ON DELETE CASCADE, so deleting a backfilled material would silently take its
purchase history and ledger with it. By downgrade time a box's material may well
carry both. The downgrade therefore drops the columns, the FK and the unique
constraint only; the backfilled materials remain as ordinary zero-cost materials
and become visible in the pre-WH-1 materials list (they have no `category` column
to hide behind any more). Full cleanup is deliberately NOT automated: deciding
which of them are disposable requires looking at their ledgers, which is a judgement
call, not a migration.

Revision ID: e9b2f4c7a318
Revises: d7f3a1c85e92
Create Date: 2026-08-07
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e9b2f4c7a318"
down_revision: Union[str, None] = "d7f3a1c85e92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


logger = logging.getLogger("alembic.runtime.migration")

LINK_TABLE = "wh1_packaging_material_link"

LINK_TABLE_DDL = f"""
CREATE TABLE IF NOT EXISTS {LINK_TABLE} (
    material_id      UUID PRIMARY KEY,
    box_id           UUID UNIQUE,
    category         VARCHAR(20) NOT NULL,
    is_stock_tracked BOOLEAN NOT NULL
)
"""

# Frozen rule-4 values for a backfilled packaging material. Boxes are counted in
# pieces and bought in hryvnia; cost and stock start at zero and move only through
# receipts, exactly like every other material.
_MATERIAL_DEFAULTS = {
    "unit": "шт",
    "currency": "UAH",
    "current_unit_cost": 0,
    "stock_quantity": 0,
    "low_stock_threshold": 0,
    "waste_percent": 0,
    "category": "PACKAGING",
    "is_stock_tracked": True,
    "is_active": True,
}


def upgrade() -> None:
    conn = op.get_bind()

    # 1. The two new material columns. server_default so existing rows are legal
    #    under NOT NULL without a rewrite pass, and so the raw SQL below can omit
    #    them; the model carries the matching Python-side default.
    op.add_column(
        "materials",
        sa.Column(
            "category",
            sa.String(length=20),
            server_default="MATERIAL",
            nullable=False,
        ),
    )
    op.add_column(
        "materials",
        sa.Column(
            "is_stock_tracked",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )

    # 2. The link column, nullable until the backfill has filled it (the
    #    add-nullable → backfill → tighten shape of d7f3a1c85e92).
    op.add_column(
        "packaging_boxes",
        sa.Column("material_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # 3. Restore anything a previous downgrade parked in the carrier table. Both
    #    statements match nothing on a virgin database.
    op.execute(LINK_TABLE_DDL)
    restored = conn.execute(
        sa.text(
            f"""
            UPDATE packaging_boxes b
            SET material_id = k.material_id
            FROM {LINK_TABLE} k
            JOIN materials m ON m.id = k.material_id
            WHERE b.id = k.box_id
            """
        )
    ).rowcount
    conn.execute(
        sa.text(
            f"""
            UPDATE materials m
            SET category = k.category, is_stock_tracked = k.is_stock_tracked
            FROM {LINK_TABLE} k
            WHERE m.id = k.material_id
            """
        )
    )

    # 4. Backfill the boxes that are still unlinked. Ids are minted into the
    #    carrier first so the INSERT and the UPDATE agree on them without a
    #    RETURNING round-trip, and so a partially-applied run is resumable.
    conn.execute(
        sa.text(
            f"""
            INSERT INTO {LINK_TABLE} (material_id, box_id, category, is_stock_tracked)
            SELECT gen_random_uuid(), id, :category, :is_stock_tracked
            FROM packaging_boxes
            WHERE material_id IS NULL
            """
        ),
        {
            "category": _MATERIAL_DEFAULTS["category"],
            "is_stock_tracked": _MATERIAL_DEFAULTS["is_stock_tracked"],
        },
    )
    created = conn.execute(
        sa.text(
            f"""
            INSERT INTO materials (
                id, name, unit, currency, current_unit_cost, stock_quantity,
                low_stock_threshold, waste_percent, supplier_name, supplier_sku,
                notes, is_active, category, is_stock_tracked
            )
            SELECT
                k.material_id, b.name, :unit, :currency, :current_unit_cost,
                :stock_quantity, :low_stock_threshold, :waste_percent, NULL, NULL,
                NULL, :is_active, :category, :is_stock_tracked
            FROM {LINK_TABLE} k
            JOIN packaging_boxes b ON b.id = k.box_id
            WHERE b.material_id IS NULL
            """
        ),
        _MATERIAL_DEFAULTS,
    ).rowcount
    conn.execute(
        sa.text(
            f"""
            UPDATE packaging_boxes b
            SET material_id = k.material_id
            FROM {LINK_TABLE} k
            WHERE b.id = k.box_id AND b.material_id IS NULL
            """
        )
    )

    # 5. Belt and braces: a restored material comes back with the column's
    #    'MATERIAL' server default, and step 3 only re-tags rows the carrier still
    #    knows about. Anything a box points at is packaging by definition.
    conn.execute(
        sa.text(
            """
            UPDATE materials SET category = 'PACKAGING'
            WHERE id IN (
                SELECT material_id FROM packaging_boxes WHERE material_id IS NOT NULL
            )
            """
        )
    )

    # 6. Tighten. The backfill is provably total — every box either kept a restored
    #    link or got a freshly minted one — so NOT NULL cannot fail here.
    op.alter_column("packaging_boxes", "material_id", nullable=False)
    op.create_unique_constraint(
        "uq_packaging_boxes_material_id", "packaging_boxes", ["material_id"]
    )
    op.create_foreign_key(
        "fk_packaging_boxes_material_id",
        "packaging_boxes",
        "materials",
        ["material_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 7. Carrier consumed.
    op.execute(f"DROP TABLE IF EXISTS {LINK_TABLE}")

    total = conn.execute(sa.text("SELECT count(*) FROM packaging_boxes")).scalar_one()
    logger.info(
        "WH-1: %d packaging box(es) — %d material(s) created, %d link(s) restored.",
        total,
        created,
        restored,
    )


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Park what the schema is about to forget: which material backs which box,
    #    and every operator classification/flag that only these two columns hold.
    #    Read BEFORE the columns are dropped. A re-upgrade consumes this table.
    op.execute(LINK_TABLE_DDL)
    conn.execute(
        sa.text(
            f"""
            INSERT INTO {LINK_TABLE} (material_id, box_id, category, is_stock_tracked)
            SELECT m.id, b.id, m.category, m.is_stock_tracked
            FROM materials m
            LEFT JOIN packaging_boxes b ON b.material_id = m.id
            WHERE b.id IS NOT NULL
               OR m.is_stock_tracked = FALSE
               OR m.category <> 'MATERIAL'
            ON CONFLICT (material_id) DO NOTHING
            """
        )
    )

    # 2. Drop the link, then the two material columns. No material rows are
    #    deleted — see the module docstring.
    op.drop_constraint(
        "fk_packaging_boxes_material_id", "packaging_boxes", type_="foreignkey"
    )
    op.drop_constraint(
        "uq_packaging_boxes_material_id", "packaging_boxes", type_="unique"
    )
    op.drop_column("packaging_boxes", "material_id")
    op.drop_column("materials", "is_stock_tracked")
    op.drop_column("materials", "category")

    parked = conn.execute(sa.text(f"SELECT count(*) FROM {LINK_TABLE}")).scalar_one()
    logger.warning(
        "WH-1 downgrade: %d material(s) parked in %s for a future re-upgrade. "
        "Backfilled packaging materials were NOT deleted (their receipts and "
        "movements cascade) and now appear as ordinary materials.",
        parked,
        LINK_TABLE,
    )
