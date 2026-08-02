"""add plaintext app_settings value + fx_rate_audit (FX-CONVERSION)

Two changes, both in service of storing the UAH/USD rate configuration.

1. `app_settings` gains a plaintext `value` column, `value_encrypted` becomes
   nullable, and a CHECK enforces that exactly one of the two is populated.

   Until now every value in this table was Fernet-encrypted, because every value
   was a secret. An exchange rate is not: it is a public number published by the
   National Bank. Encrypting it would be actively harmful — `decrypt_value`
   swallows InvalidToken and returns None (services/address_validation.py), so an
   ENCRYPTION_KEY rotation would silently stop COGS booking with no error anywhere.

   Existing rows (Google key, WesternBid pair) have value_encrypted NOT NULL and
   value NULL, so `num_nonnulls(value, value_encrypted) = 1` holds for all of them
   and the constraint applies without a data fix-up. Note that an empty-string
   value_encrypted is non-null and therefore also passes — the CHECK enforces
   "exactly one column is in use", not "the value is meaningful".

   Making value_encrypted nullable does weaken a guarantee: nothing at the schema
   level now stops a future secret being written to the plaintext column. That is
   re-asserted at the test level instead — see SECRET_SETTING_KEYS /
   PLAINTEXT_SETTING_KEYS in models/app_setting.py and
   tests/test_app_settings_storage.py.

2. New `fx_rate_audit` table — append-only, one row per rate change.

   The rate silently re-prices every SUBSEQUENT shipment and the sprint is
   forward-only (already-booked orders never move), so when a bad rate is found
   after the fact this table is the only thing that can answer "which window was
   booked at it". `app_settings.updated_by_id` records the last writer and nothing
   else. Mirrors access_audit.

REVERSIBILITY — read before downgrading. `downgrade()` restores
value_encrypted NOT NULL, which FAILS while any plaintext-only row exists. It
therefore DELETES the FX rows first (they are re-fetchable from NBU within a day,
and a manual override is a one-field re-entry). The fx_rate_audit history is
dropped with the table and is NOT recoverable — that is the accepted cost of a
downgrade here.

Revision ID: c4f1a83e6b27
Revises: b7e2d4a19f36
Create Date: 2026-08-02 16:41:03.882714
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f1a83e6b27'
down_revision: Union[str, None] = 'b7e2d4a19f36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Keys owned by FX-CONVERSION, stored in the plaintext column. Kept in sync with
# PLAINTEXT_SETTING_KEYS in models/app_setting.py.
FX_KEYS = (
    'fx_source_url',
    'fx_uah_per_usd_override',
    'fx_uah_per_usd_cached',
    'fx_rate_date',
    'fx_fetched_at',
)


def upgrade() -> None:
    op.add_column('app_settings', sa.Column('value', sa.Text(), nullable=True))
    op.alter_column('app_settings', 'value_encrypted', existing_type=sa.Text(), nullable=True)
    op.create_check_constraint(
        'ck_app_settings_exactly_one_value',
        'app_settings',
        'num_nonnulls(value, value_encrypted) = 1',
    )

    op.create_table(
        'fx_rate_audit',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=False),
        sa.Column('setting_key', sa.String(length=100), nullable=False),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_fx_rate_audit_setting_key', 'fx_rate_audit', ['setting_key'], unique=False
    )
    op.create_index(
        'ix_fx_rate_audit_created_at', 'fx_rate_audit', ['created_at'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_fx_rate_audit_created_at', table_name='fx_rate_audit')
    op.drop_index('ix_fx_rate_audit_setting_key', table_name='fx_rate_audit')
    op.drop_table('fx_rate_audit')

    op.drop_constraint('ck_app_settings_exactly_one_value', 'app_settings', type_='check')
    # Plaintext-only rows must go before value_encrypted can be NOT NULL again.
    # Scoped to the FX keys rather than a blanket `value IS NOT NULL` so a row
    # added by some later feature is not silently destroyed by this downgrade —
    # if one exists, the ALTER below fails loudly instead.
    op.execute(
        sa.text(
            "DELETE FROM app_settings WHERE key IN :keys"
        ).bindparams(sa.bindparam('keys', value=FX_KEYS, expanding=True))
    )
    op.alter_column('app_settings', 'value_encrypted', existing_type=sa.Text(), nullable=False)
    op.drop_column('app_settings', 'value')
