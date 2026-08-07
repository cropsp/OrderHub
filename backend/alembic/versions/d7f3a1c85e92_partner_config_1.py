"""PARTNER-CONFIG-1: partner entity, per-shop config, FX-aware settlement bases

Adds:
  - two labels to the EXISTING PG enum `partner_settlement_formula`: 'turnover'
    and 'profit';
  - `partners` — global partner identity, one row per person across all shops;
  - `shop_partner_config` — (shop, partner) -> percent / basis / settlement currency;
  - `partner_config_audit` — append-only record of who changed that configuration;
  - `partner_settlements.partner_id`, `partner_settlements.fx_rate_used`,
    `partner_payments.partner_id`;
  - a backfill of `partners` from the DISTINCT `partner_name` values already in
    both tables, plus `partner_id` on both.

ENUM MECHANICS — why this migration is shaped the way it is
───────────────────────────────────────────────────────────
This is the FIRST migration in the repo to extend an existing PG enum. Every
earlier enum shipped complete via create_table (CLAUDE.md: "No enum value has
ever been added post-hoc").

PostgreSQL 16 (docker-compose.yml) DOES allow `ALTER TYPE ... ADD VALUE` inside a
transaction block — the pre-12 restriction is gone, so alembic's single wrapping
transaction (alembic/env.py `with context.begin_transaction()`) is fine and no
autocommit engine is needed. What PG still forbids is *using* a newly added value
in the same transaction that added it:

    ERROR: unsafe use of new value "profit" of enum type partner_settlement_formula
    HINT:  New enum values must be committed before they can be used.

"Use" means an INSERT/UPDATE of the literal, a comparison against it, a column
DEFAULT, or a CHECK naming it. Declaring a column of the type, indexing it, or
adding a foreign key is NOT a use.

This migration therefore NEVER WRITES 'turnover' OR 'profit'. Config rows are
created by the owner in the UI after deploy; the one pre-existing settlement keeps
`revenue_items_minus_fees` (its formula is deliberately NOT migrated — it will be
deleted and recreated through the UI). Two consequences that look like omissions
and are not:

  * `shop_partner_config.basis` has NO server_default;
  * `shop_partner_config` has NO CHECK restricting `basis` to the two new values,
    even though only those two are selectable. That restriction lives in
    `schemas/partner_payout.py` (SelectableBasisLiteral) instead.

Adding either would fail this migration.

STANDING RULE for every FUTURE migration: alembic/env.py does not set
`transaction_per_migration=True`, so one `alembic upgrade head` runs ALL pending
revisions in ONE transaction. A later migration that writes 'turnover'/'profit'
would pass on an already-upgraded database and fail on one upgrading across both
revisions in a single batch. Do not write these values in a migration; read them
as `formula_type::text` (which is not a use of the enum value at all).

IRREVERSIBILITY — read before running downgrade
───────────────────────────────────────────────
`ALTER TYPE ... ADD VALUE` has no inverse: PostgreSQL has no DROP VALUE. The
downgrade below drops every table, column, index and FK this migration added but
DELIBERATELY LEAVES the two enum labels in place. The schema is therefore not
bit-identical after a down/up round trip. The residue is inert: no column defaults
to them, no CHECK references them, and after downgrade no code can produce them.

`ADD VALUE IF NOT EXISTS` is what makes the round trip
`alembic upgrade head && alembic downgrade -1 && alembic upgrade head` clean — the
re-upgrade no-ops on the labels instead of erroring.

If the labels genuinely must be removed, the only route is the rename dance, all
in one transaction:

    ALTER TYPE partner_settlement_formula RENAME TO partner_settlement_formula_old;
    CREATE TYPE partner_settlement_formula AS ENUM (
        'revenue_items_minus_fees', 'net_profit_product_only');
    ALTER TABLE partner_settlements
      ALTER COLUMN formula_type TYPE partner_settlement_formula
      USING formula_type::text::partner_settlement_formula;
    DROP TYPE partner_settlement_formula_old;

which is safe only because the replacement type is created in the same transaction
(the one documented exception to the use-after-add rule). It is not automated here:
it rewrites `partner_settlements` under ACCESS EXCLUSIVE and turns a readable
precondition failure into a mid-DDL cast error.

If any settlement already uses 'turnover' or 'profit', downgrade() REFUSES with a
RuntimeError rather than dropping money rows or leaving rows the older two-member
Python enum cannot deserialise. Delete those settlements through the UI first —
they are immutable and delete-and-recreate is the sanctioned correction path —
then re-run.

Revision ID: d7f3a1c85e92
Revises: c7e1b4d93f28
Create Date: 2026-08-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d7f3a1c85e92"
down_revision: Union[str, None] = "c7e1b4d93f28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Reuses the EXISTING type. create_type=False suppresses BOTH the implicit
# CREATE TYPE that create_table would emit (which would fail with "type
# partner_settlement_formula already exists") and the implicit DROP TYPE on
# drop_table (which would try to drop a type partner_settlements still uses).
FORMULA_ENUM = postgresql.ENUM(
    "revenue_items_minus_fees",
    "net_profit_product_only",
    "turnover",
    "profit",
    name="partner_settlement_formula",
    create_type=False,
)


def upgrade() -> None:
    # 1. The two new labels. Legal inside alembic's transaction on PG16 precisely
    #    because nothing below USES them. IF NOT EXISTS is what makes a re-upgrade
    #    after a downgrade a no-op instead of an error.
    op.execute(
        "ALTER TYPE partner_settlement_formula ADD VALUE IF NOT EXISTS 'turnover'"
    )
    op.execute(
        "ALTER TYPE partner_settlement_formula ADD VALUE IF NOT EXISTS 'profit'"
    )

    # 2. Global partner identity. One person = one row = one aggregate balance,
    #    however many shops he works on.
    op.create_table(
        "partners",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Nullable: the rows this migration creates by deduplicating historical
        # partner_name values were not created by any human, and resolving the
        # persistent system user from inside a migration buys nothing here.
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_partners_name"),
    )

    # 3. Per-shop config. `basis` reuses the existing type (create_type=False);
    #    no server_default and no CHECK on the new values — see the docstring.
    op.create_table(
        "shop_partner_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("basis", FORMULA_ENUM, nullable=False),
        sa.Column("settlement_currency", sa.String(length=3), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "percent > 0 AND percent <= 100",
            name="ck_shop_partner_config_percent_range",
        ),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "shop_id", "partner_id", name="uq_shop_partner_config_shop_partner"
        ),
    )
    op.create_index("ix_shop_partner_config_shop", "shop_partner_config", ["shop_id"])
    op.create_index(
        "ix_shop_partner_config_partner", "shop_partner_config", ["partner_id"]
    )

    # 3b. Audit of the money configuration itself. Dedicated rather than folded
    #     into `access_audit`, whose `target_user_id` means "whose access
    #     changed" — a partner is not a user, and every query over that table
    #     reads that column as a user id.
    op.create_table(
        "partner_config_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_partner_config_audit_partner_id", "partner_config_audit", ["partner_id"]
    )
    op.create_index(
        "ix_partner_config_audit_shop_id", "partner_config_audit", ["shop_id"]
    )
    op.create_index(
        "ix_partner_config_audit_created_at", "partner_config_audit", ["created_at"]
    )

    # 4. New columns — nullable for now; step 6 tightens partner_id.
    op.add_column(
        "partner_settlements",
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # Numeric(12,6) mirrors orders.cogs_fx_rate: same quantity (UAH per 1 USD),
    # same direction, same NULL-means-no-conversion-applied semantics.
    op.add_column(
        "partner_settlements",
        sa.Column("fx_rate_used", sa.Numeric(precision=12, scale=6), nullable=True),
    )
    op.add_column(
        "partner_payments",
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # 5. Backfill. Writes NO enum values, which is what keeps step 1 legal.
    #    Idempotent both ways so the round-trip re-upgrade is clean.
    op.execute(
        """
        INSERT INTO partners (id, name, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), n.name, TRUE, now(), now()
        FROM (
            SELECT DISTINCT partner_name AS name FROM partner_settlements
            UNION
            SELECT DISTINCT partner_name AS name FROM partner_payments
        ) AS n
        ON CONFLICT ON CONSTRAINT uq_partners_name DO NOTHING
        """
    )
    op.execute(
        "UPDATE partner_settlements s SET partner_id = p.id "
        "FROM partners p WHERE p.name = s.partner_name AND s.partner_id IS NULL"
    )
    op.execute(
        "UPDATE partner_payments m SET partner_id = p.id "
        "FROM partners p WHERE p.name = m.partner_name AND m.partner_id IS NULL"
    )

    # 6. The backfill is provably total: partner_name is NOT NULL on both tables,
    #    the UNION covers both, and the join key is the exact string. No row can
    #    be left with a NULL partner_id, so NOT NULL cannot fail here.
    op.alter_column("partner_settlements", "partner_id", nullable=False)
    op.alter_column("partner_payments", "partner_id", nullable=False)
    op.create_foreign_key(
        "fk_partner_settlements_partner_id",
        "partner_settlements",
        "partners",
        ["partner_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_partner_payments_partner_id",
        "partner_payments",
        "partners",
        ["partner_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 7. Indexes. The first serves the per-(shop, partner) overlap guard, which
    #    runs before any aggregate on every settlement creation.
    op.create_index(
        "ix_partner_settlements_shop_partner_period",
        "partner_settlements",
        ["shop_id", "partner_id", "period_start"],
    )
    op.create_index(
        "ix_partner_settlements_partner_id", "partner_settlements", ["partner_id"]
    )
    op.create_index(
        "ix_partner_payments_partner_id", "partner_payments", ["partner_id"]
    )


def downgrade() -> None:
    # `::text` rather than an enum literal — comparing against the literal would
    # be a "use" of a value this same transaction may have just added on a
    # down-then-up cycle. Casting to text sidesteps that entirely.
    in_use = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM partner_settlements "
                "WHERE formula_type::text IN ('turnover', 'profit')"
            )
        )
        .scalar_one()
    )
    if in_use:
        raise RuntimeError(
            f"{in_use} settlement(s) use a PARTNER-CONFIG-1 formula "
            "('turnover' / 'profit'). Downgrading would leave rows the "
            "pre-PARTNER-CONFIG-1 ORM cannot deserialise. Delete those "
            "settlements in the UI first — they are immutable and "
            "delete-and-recreate is the sanctioned correction path — then re-run."
        )

    op.drop_index("ix_partner_payments_partner_id", table_name="partner_payments")
    op.drop_index(
        "ix_partner_settlements_partner_id", table_name="partner_settlements"
    )
    op.drop_index(
        "ix_partner_settlements_shop_partner_period", table_name="partner_settlements"
    )
    op.drop_constraint(
        "fk_partner_payments_partner_id", "partner_payments", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_partner_settlements_partner_id", "partner_settlements", type_="foreignkey"
    )
    op.drop_column("partner_payments", "partner_id")
    op.drop_column("partner_settlements", "fx_rate_used")
    op.drop_column("partner_settlements", "partner_id")
    op.drop_index(
        "ix_partner_config_audit_created_at", table_name="partner_config_audit"
    )
    op.drop_index("ix_partner_config_audit_shop_id", table_name="partner_config_audit")
    op.drop_index(
        "ix_partner_config_audit_partner_id", table_name="partner_config_audit"
    )
    op.drop_table("partner_config_audit")
    op.drop_index("ix_shop_partner_config_partner", table_name="shop_partner_config")
    op.drop_index("ix_shop_partner_config_shop", table_name="shop_partner_config")
    op.drop_table("shop_partner_config")  # FK-first: before partners
    op.drop_table("partners")
    # The two enum labels are DELIBERATELY left in place — PG has no DROP VALUE.
    # See the module docstring for the rename dance if they must truly go.
