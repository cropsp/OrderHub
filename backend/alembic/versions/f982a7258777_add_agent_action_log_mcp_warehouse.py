"""add agent_action_log (MCP-WAREHOUSE)

Append-only record of writes performed by an AI agent through the MCP server.
See models/agent_action_log.py for why it exists alongside the per-row user_id
stamps the domain tables already carry.

Purely additive: one new table, three indexes. Downgrade drops them cleanly.

NOTE: autogenerate also proposed dropping `country_cleanup_backup`,
`etsy_country_backfill_backup`, `cust_country_cleanup_backup` and the
`ix_wb_parcel_last_seen_at` index — pre-existing drift between the DB and the
models (data-migration backup tables that were deliberately never modelled).
Those drops were removed by hand; they are not this sprint's business and
dropping them would be destructive.

Revision ID: f982a7258777
Revises: a4c6e8b0d2f4
Create Date: 2026-07-27 14:47:51.166649
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f982a7258777'
down_revision: Union[str, None] = 'a4c6e8b0d2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_action_log',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=False),
        sa.Column('tool', sa.String(length=64), nullable=False),
        sa.Column(
            'arguments',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='{}',
            nullable=False,
        ),
        sa.Column('ok', sa.Boolean(), nullable=False),
        sa.Column('object_type', sa.String(length=32), nullable=True),
        sa.Column('object_id', sa.String(length=64), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        # RESTRICT: the log outlives any attempt to delete the agent principal.
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_agent_action_log_actor_created',
        'agent_action_log',
        ['actor_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        op.f('ix_agent_action_log_actor_id'),
        'agent_action_log',
        ['actor_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_agent_action_log_created_at'),
        'agent_action_log',
        ['created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_action_log_created_at'), table_name='agent_action_log')
    op.drop_index(op.f('ix_agent_action_log_actor_id'), table_name='agent_action_log')
    op.drop_index('ix_agent_action_log_actor_created', table_name='agent_action_log')
    op.drop_table('agent_action_log')
