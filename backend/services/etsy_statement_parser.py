"""
OrderHub CRM — Etsy payment-account statement parser (STATEMENT-IMPORT)

Pure parsing + classification of an Etsy statement CSV. No database access, no
I/O beyond the bytes handed in — so it is cheap to test against synthetic
fixtures and reusable by the offline reconciliation script
(`scripts/reconcile_etsy_statement.py`).

The statement is the exact record of what Etsy charged. Its rows are classified
into buckets; the import service aggregates those buckets into
`order.platform_fee` and two monthly overhead rows. Nothing is ever dropped
silently: an unrecognised row aborts the whole parse (see "Fail loud" below).

Column semantics, verified over six real monthly statements (2,728 rows):

  Date         "January 30, 2026" — the CHARGE date, always inside one calendar
               month per file. Month attribution uses this, never a date quoted
               inside `Info` (a Jan-1 row bills Dec-31 click-throughs).
  Type         Sale | Tax | Fee | VAT | Marketing | Deposit | Buyer Fee | Refund
  Title        free text; carries the order number on Sale/Refund rows and the
               payout amount on Deposit rows
  Info         free text; carries the order or listing number on most rows
  Currency     always USD in every observed row — asserted, never converted
  Amount       populated on Sale/Refund only
  Fees & Taxes populated on Fee/VAT/Marketing/Tax/Buyer Fee only
  Net          == Amount + Fees & Taxes on every observed row; the value we sum
  Tax Details  always "--"

Signed sums, never `abs()`. Credits are stored by Etsy as POSITIVE values (a
refunded fee, a cancelled listing). Taking absolute values books a refund as
extra cost — the defect this parser exists to avoid.

Fail loud: an unknown `Type`, a `Marketing` title matching neither the offsite
nor the Etsy-Ads rule, an `Info` carrying an unrecognised identifier, a non-USD
row, or a file spanning more than one calendar month each raise
`StatementParseError` naming the offending row. Silently dropping a row is how a
whole class of accounting bug hides: matching on `Title == "Etsy Ads"` alone,
for instance, drops the "Credit for Etsy Ads" rows.
"""

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

# --- Buckets ---------------------------------------------------------------
# Every parsed row carries exactly one of these. The three aggregation sets
# below are the whole accounting split; anything outside them is stored for
# provenance and cross-checks but never booked.

BUCKET_SALE = "sale"
BUCKET_TAX = "tax"
BUCKET_FEE_ORDER = "fee_order"
BUCKET_FEE_ACCOUNT = "fee_account"
BUCKET_VAT_FEE_ORDER = "vat_fee_order"
BUCKET_VAT_FEE_ACCOUNT = "vat_fee_account"
BUCKET_VAT_ADS = "vat_ads"
BUCKET_ADS_OFFSITE = "ads_offsite"
BUCKET_ADS_ETSY = "ads_etsy"
BUCKET_DEPOSIT = "deposit"
BUCKET_BUYER_FEE = "buyer_fee"
BUCKET_REFUND = "refund"

#: Booked to `order.platform_fee` (the per-sale transaction cost).
PLATFORM_FEE_BUCKETS = frozenset({BUCKET_FEE_ORDER, BUCKET_VAT_FEE_ORDER})

#: Booked to the monthly "Etsy Ads" overhead row. Advertising is discretionary
#: marketing spend, not a per-sale fee — including its VAT, which follows the
#: line it taxes (decision 2026-08-04). Offsite rows keep their order id so
#: per-order ad attribution stays queryable without re-parsing.
ADS_OVERHEAD_BUCKETS = frozenset(
    {BUCKET_ADS_OFFSITE, BUCKET_ADS_ETSY, BUCKET_VAT_ADS}
)

#: Booked to the monthly "Etsy listing & account fees" overhead row. Listing and
#: auto-renew fees are real Etsy costs that carry no order number, so they can
#: never reach a per-order fee; without this bucket they would vanish and the
#: reconciliation could not tie.
ACCOUNT_FEE_OVERHEAD_BUCKETS = frozenset(
    {BUCKET_FEE_ACCOUNT, BUCKET_VAT_FEE_ACCOUNT}
)

EXPECTED_CURRENCY = "USD"

REQUIRED_COLUMNS = ("Date", "Type", "Title", "Info", "Currency", "Amount", "Net")

# Locale-independent month names. `strptime("%B")` honours the process locale,
# which is not guaranteed to be English on a deploy host.
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

_DATE_RE = re.compile(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$")
_MONEY_RE = re.compile(r"^(-)?\$?([\d,]+(?:\.\d+)?)$")

# --- Identifier forms ------------------------------------------------------
# Every shape of `Info` / `Title` observed across the six statements. Order
# matters: the listing forms are tested BEFORE the order forms, because
# "renew sold auto credit: 4343151753" quotes a LISTING id in a bare
# `<words>: <digits>` shape that the lowercase order form would otherwise claim.
# (Verified: all such ids appear in the `Listing #` set and none in the
# `Order #` set.) Misreading it produces phantom unmatched orders.

_INFO_LISTING_FORMS = (
    re.compile(r"Listing #(\d+)"),
    re.compile(r"^renew sold auto credit:\s*(\d+)$", re.IGNORECASE),
)
_INFO_ORDER_FORMS = (
    re.compile(r"Order #(\d+)"),
    # Lowercase, colon, no '#'. Appears on VAT credit rows.
    re.compile(r"^order:\s*(\d+)$"),
)
_TITLE_ORDER_FORMS = (
    # "Payment for Order #N", "Refund for Order #N", "Partial refund for Order #N"
    re.compile(r"Order #(\d+)"),
)
#: `Info` shapes that legitimately carry digits but no identifier at all.
_INFO_NO_ID_FORMS = (
    re.compile(r"^Bill for click-throughs to your shop on\b"),
)

#: Deposit rows leave every money column as "--" and put the payout in the
#: Title. Lifted into `amount_signed` so the payout cross-check is a plain sum.
_DEPOSIT_AMOUNT_RE = re.compile(r"\$([\d,]+\.\d{2})\s+sent to your")


class StatementParseError(Exception):
    """A row (or the file) could not be understood. Aborts the whole import."""


@dataclass(frozen=True)
class StatementLine:
    """One CSV row, parsed and classified. Mirrors `etsy_statement_line`."""

    row_index: int
    entry_date: date
    entry_type: str
    title: str
    info: str
    currency: str
    amount_signed: Decimal | None
    fees_taxes_signed: Decimal | None
    net_signed: Decimal
    bucket: str
    order_external_id: str | None
    listing_external_id: str | None


@dataclass(frozen=True)
class ParsedStatement:
    period_month: date  # first day of the statement's calendar month
    lines: list[StatementLine]
    file_sha256: str


def parse_statement_csv(content: bytes, filename: str = "") -> ParsedStatement:
    """Parse + classify an Etsy statement CSV.

    Raises `StatementParseError` on anything unrecognised — see module docstring.
    """
    file_sha256 = hashlib.sha256(content).hexdigest()

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:  # pragma: no cover - defensive
        raise StatementParseError(f"{filename or 'file'} is not valid UTF-8: {exc}")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise StatementParseError(f"{filename or 'file'} is empty")

    missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise StatementParseError(
            f"{filename or 'file'} is missing expected column(s): {', '.join(missing)}. "
            f"Found: {', '.join(reader.fieldnames)}"
        )

    lines: list[StatementLine] = []
    for row_index, row in enumerate(reader):
        lines.append(_parse_row(row_index, row, filename))

    if not lines:
        raise StatementParseError(f"{filename or 'file'} contains no data rows")

    period_month = _derive_period(lines, filename)
    return ParsedStatement(
        period_month=period_month, lines=lines, file_sha256=file_sha256
    )


def _parse_row(row_index: int, row: dict, filename: str) -> StatementLine:
    entry_type = (row.get("Type") or "").strip()
    title = (row.get("Title") or "").strip()
    info = (row.get("Info") or "").strip()
    currency = (row.get("Currency") or "").strip().upper()

    def fail(message: str) -> StatementParseError:
        return StatementParseError(
            f"{filename or 'statement'} row {row_index + 2}: {message} "
            f"[Type={entry_type!r} Title={title!r} Info={info!r}]"
        )

    if not currency:
        raise fail("missing Currency")
    if currency != EXPECTED_CURRENCY:
        # Deliberately not converted: `platform_fee` is stored in the order's
        # own currency, and a silently converted fee would be unauditable.
        # FX-CONVERSION is a COGS-side UAH->USD mechanism and does not apply.
        raise fail(
            f"currency {currency!r} is not {EXPECTED_CURRENCY} — mixed-currency "
            "statements are not supported; import aborted rather than converted"
        )

    entry_date = _parse_date(row.get("Date"), fail)
    amount_signed = _parse_money(row.get("Amount"), "Amount", fail)
    fees_taxes_signed = _parse_money(row.get("Fees & Taxes"), "Fees & Taxes", fail)
    net_signed = _parse_money(row.get("Net"), "Net", fail)

    order_external_id, listing_external_id = _extract_identifiers(
        entry_type, title, info, fail
    )
    bucket = _classify(entry_type, title, order_external_id, fail)

    if bucket == BUCKET_DEPOSIT and amount_signed is None:
        # Etsy leaves every money column "--" on a payout and puts the amount in
        # the Title. Lift it so the payout cross-check is a plain SUM over the
        # deposit bucket. This is the one derived value in the table.
        match = _DEPOSIT_AMOUNT_RE.search(title)
        if match:
            amount_signed = Decimal(match.group(1).replace(",", ""))

    return StatementLine(
        row_index=row_index,
        entry_date=entry_date,
        entry_type=entry_type,
        title=title,
        info=info,
        currency=currency,
        amount_signed=amount_signed,
        fees_taxes_signed=fees_taxes_signed,
        # "--" in every money column (Deposit) means "no value", i.e. zero cost.
        net_signed=net_signed if net_signed is not None else Decimal("0.00"),
        bucket=bucket,
        order_external_id=order_external_id,
        listing_external_id=listing_external_id,
    )


def _parse_date(raw: str | None, fail) -> date:
    value = (raw or "").strip()
    match = _DATE_RE.match(value)
    if not match:
        raise fail(f"unrecognised Date {value!r} (expected e.g. 'January 30, 2026')")
    month = _MONTHS.get(match.group(1).lower())
    if month is None:
        raise fail(f"unrecognised month name in Date {value!r}")
    try:
        return date(int(match.group(3)), month, int(match.group(2)))
    except ValueError as exc:
        raise fail(f"invalid Date {value!r}: {exc}")


def _parse_money(raw: str | None, column: str, fail) -> Decimal | None:
    """Signed Decimal, or None for Etsy's "--" placeholder."""
    value = (raw or "").strip()
    if value in ("", "--"):
        return None
    match = _MONEY_RE.match(value)
    if not match:
        raise fail(f"unrecognised {column} value {value!r}")
    try:
        amount = Decimal(match.group(2).replace(",", ""))
    except InvalidOperation:
        raise fail(f"unrecognised {column} value {value!r}")
    return -amount if match.group(1) else amount


def _extract_identifiers(
    entry_type: str, title: str, info: str, fail
) -> tuple[str | None, str | None]:
    """Resolve (order_external_id, listing_external_id) from Info, then Title.

    Listing forms are tested first — see the note on `_INFO_LISTING_FORMS`.
    """
    for pattern in _INFO_LISTING_FORMS:
        match = pattern.search(info)
        if match:
            return None, match.group(1)

    for pattern in _INFO_ORDER_FORMS:
        match = pattern.search(info)
        if match:
            return match.group(1), None

    if info and not any(p.search(info) for p in _INFO_NO_ID_FORMS):
        if any(ch.isdigit() for ch in info):
            raise fail(
                f"Info {info!r} carries digits but matches no known identifier "
                "form — refusing to guess whether it is an order or a listing"
            )

    # Sale / Refund rows leave Info empty and carry the order in the Title.
    for pattern in _TITLE_ORDER_FORMS:
        match = pattern.search(title)
        if match:
            return match.group(1), None

    return None, None


def _classify(entry_type: str, title: str, order_external_id: str | None, fail) -> str:
    lowered = title.lower()

    if entry_type == "Sale":
        return BUCKET_SALE
    if entry_type == "Tax":
        # Buyer sales tax is pass-through: excluded from base and from fees.
        return BUCKET_TAX
    if entry_type == "Deposit":
        return BUCKET_DEPOSIT
    if entry_type == "Buyer Fee":
        # Colorado retail delivery fee — buyer-paid, excluded from base and fees.
        return BUCKET_BUYER_FEE
    if entry_type == "Refund":
        # Parsed, stored and reported; revenue handling is a separate sprint.
        return BUCKET_REFUND

    if entry_type == "Fee":
        return BUCKET_FEE_ORDER if order_external_id else BUCKET_FEE_ACCOUNT

    if entry_type == "VAT":
        if "ads" in lowered:
            # "VAT: Etsy Ads", "VAT: Offsite Ads fee", "VAT: Offsite Ads fee credit"
            return BUCKET_VAT_ADS
        return BUCKET_VAT_FEE_ORDER if order_external_id else BUCKET_VAT_FEE_ACCOUNT

    if entry_type == "Marketing":
        # Substring matching, NOT equality: "Credit for Etsy Ads" and "Credit for
        # Offsite Ads fee" are real rows that an equality test drops silently.
        if "offsite" in lowered:
            return BUCKET_ADS_OFFSITE
        if "etsy ads" in lowered:
            return BUCKET_ADS_ETSY
        raise fail(
            "Marketing row matches neither the Offsite nor the Etsy Ads rule — "
            "refusing to guess which advertising bucket it belongs to"
        )

    raise fail(f"unknown Type {entry_type!r}")


def _derive_period(lines: list[StatementLine], filename: str) -> date:
    """The statement's calendar month, derived from the rows themselves.

    The file carries no period column. Every observed statement covers exactly
    one calendar month, and the import replaces a whole period at a time, so a
    file spanning two months has no well-defined identity — abort rather than
    guess.
    """
    months = {(line.entry_date.year, line.entry_date.month) for line in lines}
    if len(months) > 1:
        rendered = ", ".join(f"{y:04d}-{m:02d}" for y, m in sorted(months))
        raise StatementParseError(
            f"{filename or 'statement'} spans more than one calendar month "
            f"({rendered}). Import one month per file — the period is the "
            "import's idempotency key."
        )
    year, month = months.pop()
    return date(year, month, 1)
