"""ADDR-VAL-1: app_settings store + order address-validation status

Adds two things:
  1. `app_settings` — a small global key/value store for app-level settings whose
     values are Fernet-encrypted (currently just the Google Address Validation API
     key). Distinct from the per-shop NP/Shopify key columns on `shops`.
  2. `orders.address_validation_status` / `_at` — the derived, advisory outcome of an
     address check. Not a cache of Google's response; no raw content is stored.

Note on the enum: unlike `create_table`, `op.add_column` does NOT emit CREATE TYPE for
a sa.Enum — the ALTER TABLE fails with 'type "address_validation_status" does not
exist'. So the type is created and dropped explicitly here. This is the first
migration in the repo to attach a new enum to an existing table; every earlier enum
arrived via create_table, which is why the pattern differs.

Downgrade is lossless: it discards only derived validation outcomes (re-checkable on
demand) and any stored API key, which the owner re-enters via Settings.

Revision ID: b8e2f5a91c34
Revises: f2a9c4d7e1b8
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8e2f5a91c34"
down_revision: Union[str, None] = "f2a9c4d7e1b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADDRESS_VALIDATION_STATUS = sa.Enum(
    "verified",
    "needs_attention",
    "couldnt_verify",
    "unsupported",
    "ua",
    "unavailable",
    name="address_validation_status",
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value_encrypted", sa.Text(), nullable=False),
        sa.Column("last4", sa.String(length=4), nullable=True),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
        sa.ForeignKeyConstraint(
            ["updated_by_id"], ["users.id"], name="fk_app_settings_updated_by_id"
        ),
    )

    ADDRESS_VALIDATION_STATUS.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "orders",
        sa.Column("address_validation_status", ADDRESS_VALIDATION_STATUS, nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("address_validation_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "address_validation_at")
    op.drop_column("orders", "address_validation_status")
    # drop_column leaves the enum type behind — remove it so a re-run of upgrade()
    # does not hit "type already exists".
    ADDRESS_VALIDATION_STATUS.drop(op.get_bind(), checkfirst=True)

    op.drop_table("app_settings")
