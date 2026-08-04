"""add etsy_statement_line + overhead receipt source_ref (STATEMENT-IMPORT)

Two additive changes so the Etsy payment-account statement can be imported into
exact per-order fees and monthly advertising overhead.

1. NEW TABLE `etsy_statement_line` — one row per statement CSV row, stored
   verbatim with its SIGNED amount and a classification bucket. `platform_fee` is
   derived as an aggregate over these rows rather than written blind, because
   statements overlap: a July statement can carry a credit against a June order,
   so the fee must stay recomputable from everything accumulated so far.

   Idempotency key is `(shop_id, period_month, row_index)`. `row_index` is the
   0-based position in the source file and exists so that byte-identical rows
   BOTH survive — Etsy emits genuinely-separate charges that are identical on
   every visible field (158 such copies worth $14.00 across Jan-Jun 2026, mostly
   $0.04 auto-renew VAT and $0.20 listing fees). Keying on a content hash would
   collapse them and under-book the fee.

   An import replaces a whole `(shop_id, period_month)` at a time — DELETE then
   re-INSERT — which is also what makes a re-issued statement correct: rows that
   disappeared from the re-issue are gone, whereas an upsert-only strategy would
   leave them behind forever.

   Money columns are Numeric(12,2), matching the statement's own precision and
   `overhead_material_receipts.total_cost`. They are SIGNED: credits arrive from
   Etsy as positive values and must stay positive.

2. NEW COLUMN `overhead_material_receipts.source_ref` — String(120), nullable,
   with a PARTIAL UNIQUE index on `(shop_id, source_ref) WHERE source_ref IS NOT
   NULL`. It marks a receipt as owned by an automated importer so re-import
   updates that row instead of appending a second one (the ads/account-fee rows
   are one-per-shop-per-month by design). Every existing receipt is hand-entered
   and stays NULL, so the partial index excludes the entire current table and no
   existing row can collide.

REVERSIBILITY. Downgrade drops the table and the column outright. That is
lossless for OrderHub's own data — the statement lines are a re-importable
projection of files kept outside the repo, and `source_ref` is only a marker.
BUT note what downgrade does NOT undo: any `orders.platform_fee` values and any
`overhead_material_receipts` rows this import wrote remain, and after the drop
they can no longer be traced back to the lines that produced them. If you are
rolling back to undo an import's effects, delete the marked overhead receipts
(`source_ref LIKE 'etsy-stmt:%'`) and NULL the affected fees FIRST, while the
line table still explains which rows they are.

Revision ID: f2b8d6c40a15
Revises: e1a4c7b93d28
Create Date: 2026-08-04 13:22:41.905117
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b8d6c40a15'
down_revision: Union[str, None] = 'e1a4c7b93d28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'etsy_statement_line',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('shop_id', sa.UUID(), nullable=False),
        sa.Column('period_month', sa.Date(), nullable=False),
        sa.Column('row_index', sa.Integer(), nullable=False),
        sa.Column('entry_date', sa.Date(), nullable=False),
        sa.Column('entry_type', sa.String(length=32), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('info', sa.Text(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('amount_signed', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('fees_taxes_signed', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('net_signed', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('bucket', sa.String(length=24), nullable=False),
        sa.Column('order_external_id', sa.String(length=64), nullable=True),
        sa.Column('listing_external_id', sa.String(length=64), nullable=True),
        sa.Column('order_id', sa.UUID(), nullable=True),
        sa.Column('source_filename', sa.String(length=255), nullable=True),
        sa.Column('file_sha256', sa.String(length=64), nullable=True),
        sa.Column(
            'imported_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('imported_by_user_id', sa.UUID(), nullable=False),
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
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['imported_by_user_id'], ['users.id'], ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'shop_id',
            'period_month',
            'row_index',
            name='uq_etsy_statement_line_shop_period_row',
        ),
    )
    op.create_index(
        op.f('ix_etsy_statement_line_shop_id'),
        'etsy_statement_line',
        ['shop_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_etsy_statement_line_order_id'),
        'etsy_statement_line',
        ['order_id'],
        unique=False,
    )
    op.create_index(
        'ix_etsy_statement_line_shop_order_external',
        'etsy_statement_line',
        ['shop_id', 'order_external_id'],
        unique=False,
    )
    op.create_index(
        'ix_etsy_statement_line_shop_period',
        'etsy_statement_line',
        ['shop_id', 'period_month'],
        unique=False,
    )

    op.add_column(
        'overhead_material_receipts',
        sa.Column('source_ref', sa.String(length=120), nullable=True),
    )
    op.create_index(
        'uq_overhead_material_receipts_shop_source_ref',
        'overhead_material_receipts',
        ['shop_id', 'source_ref'],
        unique=True,
        postgresql_where=sa.text('source_ref IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_overhead_material_receipts_shop_source_ref',
        table_name='overhead_material_receipts',
    )
    op.drop_column('overhead_material_receipts', 'source_ref')

    op.drop_index('ix_etsy_statement_line_shop_period', table_name='etsy_statement_line')
    op.drop_index(
        'ix_etsy_statement_line_shop_order_external', table_name='etsy_statement_line'
    )
    op.drop_index(
        op.f('ix_etsy_statement_line_order_id'), table_name='etsy_statement_line'
    )
    op.drop_index(
        op.f('ix_etsy_statement_line_shop_id'), table_name='etsy_statement_line'
    )
    op.drop_table('etsy_statement_line')
