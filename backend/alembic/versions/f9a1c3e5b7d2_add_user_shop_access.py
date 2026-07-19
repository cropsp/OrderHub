"""add user_shop_access + backfill (USER-ACCESS-1)

Introduces per-user shop scoping. Creates the `user_shop_access` grant table and
backfills it so today's visibility is preserved EXACTLY:

  - OWNER   → no rows (unrestricted by design; resolver short-circuits).
  - MANAGER → every active shop (matches today's unrestricted managers).
  - DESIGNER → the shops derived from their existing order assignments
               (matches the old get_shop_for_user assignment rule).

The backfill is reversible: downgrade drops the table, and because scoping is
purely additive, old code with the table gone behaves exactly as before.

DB enum `user_role` stores the uppercase member NAMES ('OWNER'/'MANAGER'/
'DESIGNER') — see the system-user migration which inserts role 'OWNER'.

Revision ID: f9a1c3e5b7d2
Revises: b8e2f5a91c34
Create Date: 2026-07-18 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9a1c3e5b7d2"
down_revision: Union[str, None] = "b8e2f5a91c34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_shop_access",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("shop_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "shop_id", name="uq_user_shop_access_user_shop"
        ),
    )
    op.create_index(
        "ix_user_shop_access_user_id", "user_shop_access", ["user_id"]
    )
    op.create_index(
        "ix_user_shop_access_shop_id", "user_shop_access", ["shop_id"]
    )

    # ── Backfill: preserve today's visibility exactly ──
    # Managers → every active shop.
    op.execute(
        """
        INSERT INTO user_shop_access (id, user_id, shop_id)
        SELECT gen_random_uuid(), u.id, s.id
        FROM users u
        CROSS JOIN shops s
        WHERE u.role = 'MANAGER' AND s.is_active = TRUE
        ON CONFLICT ON CONSTRAINT uq_user_shop_access_user_shop DO NOTHING;
        """
    )
    # Designers → the distinct shops of their existing order assignments.
    op.execute(
        """
        INSERT INTO user_shop_access (id, user_id, shop_id)
        SELECT gen_random_uuid(), a.assigned_designer_id, a.shop_id
        FROM (
            SELECT DISTINCT assigned_designer_id, shop_id
            FROM orders
            WHERE assigned_designer_id IS NOT NULL
        ) a
        JOIN users u
          ON u.id = a.assigned_designer_id AND u.role = 'DESIGNER'
        ON CONFLICT ON CONSTRAINT uq_user_shop_access_user_shop DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_user_shop_access_shop_id", table_name="user_shop_access")
    op.drop_index("ix_user_shop_access_user_id", table_name="user_shop_access")
    op.drop_table("user_shop_access")
