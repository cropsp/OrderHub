"""Backfill broken country codes on Etsy orders/customers (ETSY-COUNTRY-FIX)

services/etsy_parser.py stored `Ship Country`[:2] — the first two characters of a
full country NAME — into orders.shipping_country and customers.country. That
produced title-case pseudo-codes: "United States" -> "Un", "Germany" -> "Ge".
CTRY-1 renders stored codes via Intl.DisplayNames, so these surfaced as
"United Nations" / "Georgia" in the UI.

This migration repairs the already-imported rows. The parser fix (same sprint)
prevents new ones.

Scope guard: orders joined to shops WHERE shops.platform = 'ETSY' AND
shipping_country ~ '^[A-Z][a-z]$'. That title-case shape is only ever produced by
the truncation bug, so Shopify rows, manual rows, and correctly-coded rows
(uppercase) are never touched. On a database with no broken Etsy imports the
SELECT returns zero rows and the migration is a clean no-op.

Self-contained by design: no imports from services/. The truncation map is frozen
here so a later refactor of services/country_resolver.py cannot change what this
historical migration does.

Reversible: old values are copied to etsy_country_backfill_backup before the
UPDATE; downgrade() restores from it and drops the table.

Revision ID: c7d1e93b40af
Revises: b3f6a2c81d47
Create Date: 2026-07-15 20:40:00.000000
"""
import logging
import re
from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7d1e93b40af'
down_revision: Union[str, None] = 'b3f6a2c81d47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

BACKUP_TABLE = "etsy_country_backfill_backup"

# Unambiguous truncations: exactly one country name starts with these two chars
# among the destinations present in the data.
TRUNCATED_FIXES = {
    "Ge": "DE",  # Germany  (NOT GE/Georgia — the bug CTRY-1 surfaced)
    "Cz": "CZ",  # Czechia / Czech Republic
    "Fr": "FR",  # France
    "It": "IT",  # Italy
    "Ca": "CA",  # Canada
}

# Ambiguous truncations, disambiguated by address shape. "Un" is the only one
# present in the current data; "Au" and "Po" are handled for completeness because
# the same parser bug would produce them for Austria/Australia and Poland/Portugal.
US_STATE_RE = re.compile(r"^[A-Z]{2}$")
US_ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
AU_STATE_RE = re.compile(r"^(NSW|VIC|QLD|WA|SA|TAS|ACT|NT)$", re.IGNORECASE)
NUMERIC_ZIP_RE = re.compile(r"^\d{4,5}$")


def _looks_us(state: Optional[str], zip_: Optional[str]) -> bool:
    """US addresses carry a 2-letter state code AND a 5-digit (+4) ZIP."""
    return bool(
        US_STATE_RE.match((state or "").strip())
        and US_ZIP_RE.match((zip_ or "").strip())
    )


def _resolve_row(code: str, state: Optional[str], zip_: Optional[str]) -> Optional[str]:
    """Map one broken code to an ISO alpha-2 code, or None if not confident.

    Pure function — unit-tested in tests/test_etsy_country_backfill.py.
    """
    if code in TRUNCATED_FIXES:
        return TRUNCATED_FIXES[code]

    zip_clean = (zip_ or "").strip()

    if code == "Un":
        # "United States" vs "United Kingdom".
        if _looks_us(state, zip_):
            return "US"
        # UK postcodes are alphanumeric ("YO88SZ", "RM6 4TJ") — never all-digit.
        if zip_clean and re.search(r"[A-Za-z]", zip_clean):
            return "GB"
        return None

    if code == "Au":
        # "Austria" vs "Australia". Both use 4-digit postcodes, so the state code
        # is the only reliable signal: Australian addresses carry one, Austrian
        # ones do not.
        if AU_STATE_RE.match((state or "").strip()):
            return "AU"
        if len(zip_clean) == 4 and NUMERIC_ZIP_RE.match(zip_clean):
            return "AT"
        return None

    if code == "Po":
        # "Poland" (5-digit "NN-NNN") vs "Portugal" (7-digit "NNNN-NNN").
        if re.match(r"^\d{2}-\d{3}$", zip_clean):
            return "PL"
        if re.match(r"^\d{4}-\d{3}$", zip_clean):
            return "PT"
        return None

    return None


def upgrade() -> None:
    conn = op.get_bind()

    op.create_table(
        BACKUP_TABLE,
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("old_order_country", sa.String(length=2), nullable=True),
        sa.Column("old_customer_country", sa.String(length=2), nullable=True),
        sa.Column("new_country", sa.String(length=2), nullable=False),
        sa.Column(
            "backfilled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("order_id"),
    )

    rows = conn.execute(
        sa.text(
            """
            SELECT o.id AS order_id,
                   o.customer_id,
                   o.shipping_country,
                   o.shipping_state,
                   o.shipping_zip,
                   c.country AS customer_country
            FROM orders o
            JOIN shops s ON s.id = o.shop_id
            LEFT JOIN customers c ON c.id = o.customer_id
            WHERE s.platform = 'ETSY'
              AND o.shipping_country ~ '^[A-Z][a-z]$'
            """
        )
    ).fetchall()

    fixed: dict[str, int] = {}
    unresolved: list[tuple] = []

    for row in rows:
        new_code = _resolve_row(row.shipping_country, row.shipping_state, row.shipping_zip)

        if new_code is None:
            unresolved.append((row.order_id, row.shipping_country, row.shipping_state, row.shipping_zip))
            continue

        conn.execute(
            sa.text(
                f"""
                INSERT INTO {BACKUP_TABLE}
                    (order_id, customer_id, old_order_country, old_customer_country, new_country)
                VALUES (:order_id, :customer_id, :old_order, :old_customer, :new_code)
                """
            ),
            {
                "order_id": row.order_id,
                "customer_id": row.customer_id,
                "old_order": row.shipping_country,
                "old_customer": row.customer_country,
                "new_code": new_code,
            },
        )

        conn.execute(
            sa.text("UPDATE orders SET shipping_country = :new_code WHERE id = :order_id"),
            {"new_code": new_code, "order_id": row.order_id},
        )

        if row.customer_id is not None:
            conn.execute(
                sa.text("UPDATE customers SET country = :new_code WHERE id = :customer_id"),
                {"new_code": new_code, "customer_id": row.customer_id},
            )

        key = f"{row.shipping_country} -> {new_code}"
        fixed[key] = fixed.get(key, 0) + 1

    if not rows:
        logger.info("ETSY-COUNTRY-FIX: no broken Etsy country codes found — no-op.")
        return

    logger.info("ETSY-COUNTRY-FIX: corrected %d of %d Etsy order(s):", sum(fixed.values()), len(rows))
    for key, count in sorted(fixed.items()):
        logger.info("  %-12s %d", key, count)

    if unresolved:
        logger.warning(
            "ETSY-COUNTRY-FIX: %d row(s) left UNTOUCHED — manual review required:",
            len(unresolved),
        )
        for order_id, code, state, zip_ in unresolved:
            logger.warning("  order=%s country=%r state=%r zip=%r", order_id, code, state, zip_)


def downgrade() -> None:
    conn = op.get_bind()

    # Restore only where the current value still matches what we wrote, so a
    # country corrected by hand after the backfill is not clobbered.
    conn.execute(
        sa.text(
            f"""
            UPDATE orders o
            SET shipping_country = b.old_order_country
            FROM {BACKUP_TABLE} b
            WHERE o.id = b.order_id
              AND o.shipping_country = b.new_country
            """
        )
    )
    conn.execute(
        sa.text(
            f"""
            UPDATE customers c
            SET country = b.old_customer_country
            FROM {BACKUP_TABLE} b
            WHERE c.id = b.customer_id
              AND c.country = b.new_country
            """
        )
    )

    op.drop_table(BACKUP_TABLE)
