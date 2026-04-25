"""Add persistent system user (SEC-04)

Insert a persistent User row referenced by webhook and scheduler audit
trails. Replaces the prior pattern of (a) the scheduler fabricating an
in-memory User with id 00000000-0000-0000-0000-000000000000 and (b) the
webhook handler picking an arbitrary user via select(User).limit(1).

DO NOT DELETE this row — it is referenced by order_status_history rows
created from webhooks and the Shopify scheduler. Removing it would
cascade-fail on FK to users.id and break audit history.

Forward-fix only: existing rows pointing at the old all-zeros UUID or at
a non-deterministic limit(1) user are NOT repaired here. See SEC-04
orphan-repair entry in audit_artifacts/TECH_DEBT.md.

Revision ID: a1b2c3d4e5f6
Revises: bd752467a39b
Create Date: 2026-04-25 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'bd752467a39b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SYSTEM_USER_ID = '00000000-0000-0000-0000-000000000001'


def upgrade() -> None:
    # Idempotent: ON CONFLICT DO NOTHING so re-running on a DB that already
    # has the row (e.g. from a previously-applied dev branch) is a no-op.
    # Password starts with '!' which is not a valid bcrypt hash — verify_password
    # will always return False, so this account cannot log in.
    op.execute(
        f"""
        INSERT INTO users (
            id, email, hashed_password, full_name, role, is_active, preferences
        ) VALUES (
            '{SYSTEM_USER_ID}',
            'system@orderhub.local',
            '!disabled-system-user-not-a-bcrypt-hash',
            'System (webhooks/scheduler)',
            'OWNER',
            FALSE,
            '{{}}'
        ) ON CONFLICT (id) DO NOTHING;
        """
    )


def downgrade() -> None:
    # Refuse to delete if any order_status_history rows still reference this
    # user — losing those rows would corrupt the audit trail.
    op.execute(
        f"""
        DELETE FROM users WHERE id = '{SYSTEM_USER_ID}'
        AND NOT EXISTS (
            SELECT 1 FROM order_status_history WHERE changed_by_id = '{SYSTEM_USER_ID}'
        );
        """
    )
