"""Repair persistent system user (forward-fix)

Re-assert the invariant that migration a1b2c3d4e5f6 established: the persistent
system User row (SYSTEM_USER_ID 00000000-0000-0000-0000-000000000001) must
exist. It is the audit actor for webhook- and scheduler-created
order_status_history rows.

Nothing re-established this row after a DB was rebuilt from models, reseeded, or
the row was otherwise removed — so environments that lost it left both scheduler
jobs (run_shopify_sync / run_westernbid_poll) permanently skipping on the missing
system-user guard. This forward-fix is a NEW head, so any DB currently missing
the row is repaired on `alembic upgrade head`.

Idempotent (ON CONFLICT DO NOTHING); a no-op where the row already exists.

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-07-21 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SYSTEM_USER_ID = '00000000-0000-0000-0000-000000000001'


def upgrade() -> None:
    # Same body as a1b2c3d4e5f6.upgrade(): '!'-prefixed password is not a valid
    # bcrypt hash so the account can never authenticate; is_active FALSE.
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
    # No-op: a repair migration must never delete the audit principal. The row's
    # lifecycle is owned by a1b2c3d4e5f6 (whose downgrade already guards on
    # referencing order_status_history rows).
    pass
