"""Clean up residual ambiguous country codes (COUNTRY-CLEANUP)

ETSY-COUNTRY-FIX (c7d1e93b40af) corrected the bulk of the truncated Etsy country
codes but deliberately skipped the ambiguous name-truncations its resolver could
not disambiguate from address shape alone. Those rows still hold title-case
pseudo-codes ("Sw", "Ja", "Be", "Sp", "Ma", "Is") that CTRY-1 renders as garbage,
plus one accented case ("Tü") the prior migration never even selected because its
`^[A-Z][a-z]$` regex does not match a non-ASCII second character.

This migration repairs those residual rows. Each pseudo-code is the first two
characters of the original country NAME (e.g. "Spain" -> "Sp"), so the map reverses
the truncation:

    Be -> BE (Belgium)      Ja -> JP (Japan)        Sp -> ES (Spain)
    Is -> IL (Israel)       Ma -> MY (Malaysia)     Tü -> TR (Türkiye)

"Sw" is genuinely ambiguous (Sweden / Switzerland) and is split by postal-code
length: Swiss codes are 4 digits, Swedish codes are 5 digits. Every corroborating
signal in the data agrees (Swiss cantons/cities Chancy·Losone·Pfaffhausen vs the
Swedish city Uppsala). A "Sw" row matching neither shape resolves to None and is
reported, not guessed — same conservative stance as the prior migration.

Separately, one manual-entry customer stored the Cyrillic country "УК" (meant "UA");
that is corrected here too, scoped by value (not by UUID), so it is a clean no-op on
any database where the row is absent.

Scope guard: orders joined to shops WHERE shops.platform = 'ETSY' AND the country is
a 2-char, uppercase-first, non-ISO-2 value. That shape is only ever produced by the
truncation bug, so Shopify rows, manual rows, and correctly-coded rows are never
touched. On a database with no broken rows the SELECT returns zero rows and the
migration is a clean no-op.

Self-contained by design: no imports from services/. The truncation map is frozen
here so a later refactor of services/country_resolver.py cannot change what this
historical migration does.

Reversible: old values are copied to two backup tables before the UPDATEs;
downgrade() restores from them (only where the current value still matches what we
wrote) and drops the tables.

Revision ID: f2a9c4d7e1b8
Revises: c7d1e93b40af
Create Date: 2026-07-16 13:20:00.000000
"""
import logging
import re
from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2a9c4d7e1b8'
down_revision: Union[str, None] = 'c7d1e93b40af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

ORDER_BACKUP_TABLE = "country_cleanup_backup"
CUST_BACKUP_TABLE = "cust_country_cleanup_backup"

# The Cyrillic value a manual entry stored for Ukraine (CUST-CYRILLIC-COUNTRY).
CYRILLIC_UK = "УК"  # "УК"

# Unambiguous name-prefix truncations: exactly one plausible destination in the data
# (each verified against the row's shipping_state / shipping_city / shipping_zip).
TRUNCATED_FIXES = {
    "Be": "BE",  # Belgium   (Oost-Vlaanderen / Sint-Niklaas)
    "Is": "IL",  # Israel    (Tel Aviv)  — not Isle of Man
    "Ja": "JP",  # Japan     (Japanese prefectures) — not Jamaica
    "Ma": "MY",  # Malaysia  (Selangor) — not Malta / Malawi
    "Sp": "ES",  # Spain     (Bizkaia)
    "Tü": "TR",  # Türkiye   (Istanbul)
}

_DIGITS_RE = re.compile(r"^\d+$")


def _resolve_row(code: str, state: Optional[str], zip_: Optional[str]) -> Optional[str]:
    """Map one residual broken code to an ISO alpha-2 code, or None if not confident.

    Pure function — unit-tested in tests/test_country_cleanup.py.
    """
    if code in TRUNCATED_FIXES:
        return TRUNCATED_FIXES[code]

    if code == "Sw":
        # "Sweden" vs "Switzerland" (vs "Swaziland", not present). Split by
        # postal-code length: Switzerland uses 4-digit codes, Sweden 5-digit.
        zip_clean = (zip_ or "").strip()
        if _DIGITS_RE.match(zip_clean):
            if len(zip_clean) == 4:
                return "CH"
            if len(zip_clean) == 5:
                return "SE"
        return None

    return None


def upgrade() -> None:
    conn = op.get_bind()

    op.create_table(
        ORDER_BACKUP_TABLE,
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
    op.create_table(
        CUST_BACKUP_TABLE,
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("old_country", sa.String(length=2), nullable=True),
        sa.Column("new_country", sa.String(length=2), nullable=False),
        sa.Column(
            "backfilled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("customer_id"),
    )

    # --- 1. Residual Etsy order/customer country codes ---------------------------
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
              AND char_length(o.shipping_country) = 2
              AND o.shipping_country ~ '^[A-Z]'
              AND o.shipping_country !~ '^[A-Z]{2}$'
            """
        )
    ).fetchall()

    fixed: dict[str, int] = {}
    unresolved: list[tuple] = []

    for row in rows:
        new_code = _resolve_row(row.shipping_country, row.shipping_state, row.shipping_zip)

        if new_code is None:
            unresolved.append(
                (row.order_id, row.shipping_country, row.shipping_state, row.shipping_zip)
            )
            continue

        conn.execute(
            sa.text(
                f"""
                INSERT INTO {ORDER_BACKUP_TABLE}
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
        logger.info("COUNTRY-CLEANUP: no residual broken Etsy country codes found.")
    else:
        logger.info(
            "COUNTRY-CLEANUP: corrected %d of %d residual Etsy order(s):",
            sum(fixed.values()),
            len(rows),
        )
        for key, count in sorted(fixed.items()):
            logger.info("  %-12s %d", key, count)

        if unresolved:
            logger.warning(
                "COUNTRY-CLEANUP: %d row(s) left UNTOUCHED — manual review required:",
                len(unresolved),
            )
            for order_id, code, state, zip_ in unresolved:
                logger.warning("  order=%s country=%r state=%r zip=%r", order_id, code, state, zip_)

    # --- 2. Cyrillic "УК" customer country (CUST-CYRILLIC-COUNTRY) ----------------
    cust_rows = conn.execute(
        sa.text("SELECT id, country FROM customers WHERE country = :uk"),
        {"uk": CYRILLIC_UK},
    ).fetchall()

    for cust in cust_rows:
        conn.execute(
            sa.text(
                f"""
                INSERT INTO {CUST_BACKUP_TABLE} (customer_id, old_country, new_country)
                VALUES (:customer_id, :old_country, 'UA')
                """
            ),
            {"customer_id": cust.id, "old_country": cust.country},
        )
        conn.execute(
            sa.text("UPDATE customers SET country = 'UA' WHERE id = :customer_id"),
            {"customer_id": cust.id},
        )

    if cust_rows:
        logger.info("COUNTRY-CLEANUP: fixed %d customer(s) with country 'УК' -> 'UA'.", len(cust_rows))
    else:
        logger.info("COUNTRY-CLEANUP: no customer with Cyrillic country 'УК' found.")


def downgrade() -> None:
    conn = op.get_bind()

    # Restore only where the current value still matches what we wrote, so a value
    # corrected by hand after this migration is not clobbered.
    conn.execute(
        sa.text(
            f"""
            UPDATE orders o
            SET shipping_country = b.old_order_country
            FROM {ORDER_BACKUP_TABLE} b
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
            FROM {ORDER_BACKUP_TABLE} b
            WHERE c.id = b.customer_id
              AND c.country = b.new_country
            """
        )
    )
    conn.execute(
        sa.text(
            f"""
            UPDATE customers c
            SET country = b.old_country
            FROM {CUST_BACKUP_TABLE} b
            WHERE c.id = b.customer_id
              AND c.country = b.new_country
            """
        )
    )

    op.drop_table(CUST_BACKUP_TABLE)
    op.drop_table(ORDER_BACKUP_TABLE)
