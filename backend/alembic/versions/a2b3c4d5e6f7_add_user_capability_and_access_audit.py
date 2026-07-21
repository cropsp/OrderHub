"""add user_capability + access_audit + capability backfill (USER-ACCESS-2)

Introduces per-user money-visibility capabilities and a persistent access-audit
table.

`user_capability` holds explicit override rows (no row = role default). Backfill
preserves today's incoherent-but-real behaviour EXACTLY:

  - MANAGER → view_finance=true, view_costs=false. Today a manager reads a
    shop's full P&L via /finance (require_role OWNER,MANAGER) but is denied
    per-order costs (OWNER-only). That maps to view_finance on, view_costs off.
  - DESIGNER → no rows (both default false — designers have no money surface).
  - OWNER → no rows (superuser; resolver short-circuits to all capabilities).

NEW users created after this sprint default deny-by-default for every non-owner
role (both capabilities false) — restricting money visibility is the whole
point, so the OWNER grants explicitly. This is a deliberate divergence from the
backfilled managers, mirroring USER-ACCESS-1's new-user rule.

`access_audit` records grant/revoke of both shop access and capabilities
(actor, target, object, action, source) — the table the access_service docstring
promised.

Reversible: downgrade drops both tables. Scoping stays additive — old code with
the tables gone resolves every non-owner to the role default (deny), so nothing
crashes.

DB enum `user_role` stores uppercase member NAMES ('MANAGER' etc.) — see the
initial migration.

Revision ID: a2b3c4d5e6f7
Revises: f9a1c3e5b7d2
Create Date: 2026-07-20 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f9a1c3e5b7d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_capability",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "capability", name="uq_user_capability_user_cap"
        ),
    )
    op.create_index(
        "ix_user_capability_user_id", "user_capability", ["user_id"]
    )

    op.create_table(
        "access_audit",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("target_user_id", sa.UUID(), nullable=False),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("object_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_access_audit_target_user_id", "access_audit", ["target_user_id"]
    )
    op.create_index(
        "ix_access_audit_created_at", "access_audit", ["created_at"]
    )

    # ── Backfill: preserve today's effective money visibility ──
    # Existing managers keep P&L access (view_finance) but stay denied itemised
    # costs (view_costs) — exactly today's behaviour. Explicit rows, so they are
    # NOT affected by the new deny-by-default role default.
    op.execute(
        """
        INSERT INTO user_capability (id, user_id, capability, granted)
        SELECT gen_random_uuid(), u.id, 'view_finance', TRUE
        FROM users u
        WHERE u.role = 'MANAGER'
        ON CONFLICT ON CONSTRAINT uq_user_capability_user_cap DO NOTHING;
        """
    )
    op.execute(
        """
        INSERT INTO user_capability (id, user_id, capability, granted)
        SELECT gen_random_uuid(), u.id, 'view_costs', FALSE
        FROM users u
        WHERE u.role = 'MANAGER'
        ON CONFLICT ON CONSTRAINT uq_user_capability_user_cap DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_access_audit_created_at", table_name="access_audit")
    op.drop_index("ix_access_audit_target_user_id", table_name="access_audit")
    op.drop_table("access_audit")
    op.drop_index("ix_user_capability_user_id", table_name="user_capability")
    op.drop_table("user_capability")
