"""add_material_receipts_and_movements

Revision ID: e1c4d92a87bf
Revises: b7e2f4a91c5d
Create Date: 2026-05-14 12:00:00.000000

MAT-2: Receipts + ledger tables on top of the MAT-1 catalogs.

Adds three tables:
  - material_receipts          (immutable direct-material purchase batches)
  - overhead_material_receipts (immutable indirect expense events, optional shop_id)
  - material_movements         (append-only audit ledger; PKG-2 pattern)

Plus the `material_movement_reason` ENUM with all four values
(receipt/consumption/waste/adjustment), even though MAT-2 only emits receipt +
adjustment + waste. CONSUMPTION lands now so MAT-4 doesn't need an ALTER TYPE.

The CHECK constraint `ck_material_movement_consumption_cost` enforces that
`unit_cost_at_movement` is set iff reason='consumption' — forward-compatible
with MAT-4 even though no consumption rows are emitted yet.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1c4d92a87bf"
down_revision: Union[str, None] = "b7e2f4a91c5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_receipts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("material_id", sa.UUID(), nullable=False),
        sa.Column("qty", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("shipping_cost", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "is_initial",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("supplier", sa.String(length=200), nullable=True),
        sa.Column("invoice_no", sa.String(length=100), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_material_receipts_material_id"),
        "material_receipts",
        ["material_id"],
        unique=False,
    )

    op.create_table(
        "overhead_material_receipts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("overhead_material_id", sa.UUID(), nullable=False),
        sa.Column("shop_id", sa.UUID(), nullable=True),
        sa.Column("qty", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("total_cost", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("supplier", sa.String(length=200), nullable=True),
        sa.Column("invoice_no", sa.String(length=100), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["overhead_material_id"],
            ["overhead_materials.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_overhead_material_receipts_overhead_material_id"),
        "overhead_material_receipts",
        ["overhead_material_id"],
        unique=False,
    )
    op.create_index(
        "ix_overhead_material_receipts_shop_id_received_at",
        "overhead_material_receipts",
        ["shop_id", "received_at"],
        unique=False,
        postgresql_where=sa.text("shop_id IS NOT NULL"),
    )
    op.create_index(
        "ix_overhead_material_receipts_received_at",
        "overhead_material_receipts",
        ["received_at"],
        unique=False,
    )

    op.create_table(
        "material_movements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("material_id", sa.UUID(), nullable=False),
        sa.Column("delta", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "reason",
            sa.Enum(
                "receipt",
                "consumption",
                "waste",
                "adjustment",
                name="material_movement_reason",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("order_id", sa.UUID(), nullable=True),
        sa.Column("receipt_id", sa.UUID(), nullable=True),
        sa.Column(
            "unit_cost_at_movement",
            sa.Numeric(precision=12, scale=4),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id"],
            ["material_receipts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(reason = 'consumption' AND unit_cost_at_movement IS NOT NULL) OR "
            "(reason != 'consumption' AND unit_cost_at_movement IS NULL)",
            name="ck_material_movement_consumption_cost",
        ),
    )
    op.create_index(
        op.f("ix_material_movements_material_id"),
        "material_movements",
        ["material_id"],
        unique=False,
    )
    op.create_index(
        "ix_material_movements_order_id",
        "material_movements",
        ["order_id"],
        unique=False,
        postgresql_where=sa.text("order_id IS NOT NULL"),
    )
    op.create_index(
        op.f("ix_material_movements_created_at"),
        "material_movements",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_material_movements_created_at"),
        table_name="material_movements",
    )
    op.drop_index(
        "ix_material_movements_order_id",
        table_name="material_movements",
        postgresql_where=sa.text("order_id IS NOT NULL"),
    )
    op.drop_index(
        op.f("ix_material_movements_material_id"),
        table_name="material_movements",
    )
    op.drop_table("material_movements")
    sa.Enum(name="material_movement_reason").drop(op.get_bind(), checkfirst=False)

    op.drop_index(
        "ix_overhead_material_receipts_received_at",
        table_name="overhead_material_receipts",
    )
    op.drop_index(
        "ix_overhead_material_receipts_shop_id_received_at",
        table_name="overhead_material_receipts",
        postgresql_where=sa.text("shop_id IS NOT NULL"),
    )
    op.drop_index(
        op.f("ix_overhead_material_receipts_overhead_material_id"),
        table_name="overhead_material_receipts",
    )
    op.drop_table("overhead_material_receipts")

    op.drop_index(
        op.f("ix_material_receipts_material_id"),
        table_name="material_receipts",
    )
    op.drop_table("material_receipts")
