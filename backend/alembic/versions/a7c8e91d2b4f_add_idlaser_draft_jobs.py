"""add_idlaser_draft_jobs

Revision ID: a7c8e91d2b4f
Revises: d48f7613dd60
Create Date: 2026-05-19 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a7c8e91d2b4f'
down_revision: Union[str, None] = 'd48f7613dd60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'idlaser_draft_jobs',
        sa.Column('order_id', sa.UUID(), nullable=False),
        sa.Column('photo_attachment_id', sa.UUID(), nullable=True),
        sa.Column('result_attachment_id', sa.UUID(), nullable=True),
        sa.Column('triggered_by_id', sa.UUID(), nullable=False),
        sa.Column(
            'state',
            sa.Enum(
                'pending', 'running', 'needs_review',
                'ready', 'failed', 'cancelled',
                name='idlaser_draft_job_state',
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column('manual_corners', postgresql.JSONB(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.CheckConstraint(
            'completed_at IS NULL OR started_at IS NULL '
            'OR completed_at >= started_at',
            name='ck_idlaser_draft_jobs_completed_after_started',
        ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['photo_attachment_id'], ['attachments.id'], ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['result_attachment_id'], ['attachments.id'], ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['triggered_by_id'], ['users.id'], ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_idlaser_draft_jobs_order_state',
        'idlaser_draft_jobs',
        ['order_id', 'state'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_idlaser_draft_jobs_order_state',
        table_name='idlaser_draft_jobs',
    )
    op.drop_table('idlaser_draft_jobs')

    # Hand-edit per S004 rule 17: autogenerate does NOT drop the Postgres
    # ENUM type. Drop explicitly so the round-trip (downgrade -1 → upgrade
    # head) succeeds on a single DB without "type already exists" errors.
    sa.Enum(name='idlaser_draft_job_state').drop(
        op.get_bind(), checkfirst=True,
    )
