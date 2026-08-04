"""STATEMENT-IMPORT — Etsy statement parser regression guards.

Every fixture here is SYNTHETIC. Real statements are financial + PII data and
never enter the repo; the shapes below were derived from six real monthly files
(2,728 rows) and reproduced with invented order/listing numbers and amounts.

The regressions that matter, in order of how expensive they would be to miss:

  1. Byte-identical rows are legitimately separate charges and must ALL survive.
     Etsy emits them constantly (158 redundant copies worth $14.00 across
     Jan-Jun 2026). Keying on row content collapses them and under-books the fee.
  2. SIGNED sums, never abs(). Credits arrive as POSITIVE values; abs() books a
     refunded fee as extra cost.
  3. "renew sold auto credit: N" quotes a LISTING id in a shape that looks like
     the lowercase order form. Reading it as an order invents phantom orders.
  4. Advertising is partitioned by SUBSTRING, not equality — `Title == "Etsy Ads"`
     silently drops "Credit for Etsy Ads".
  5. Anything unrecognised aborts loudly rather than being dropped.
"""

from datetime import date
from decimal import Decimal

import pytest

from services.etsy_statement_parser import (
    ACCOUNT_FEE_OVERHEAD_BUCKETS,
    ADS_OVERHEAD_BUCKETS,
    BUCKET_ADS_ETSY,
    BUCKET_ADS_OFFSITE,
    BUCKET_BUYER_FEE,
    BUCKET_DEPOSIT,
    BUCKET_FEE_ACCOUNT,
    BUCKET_FEE_ORDER,
    BUCKET_REFUND,
    BUCKET_SALE,
    BUCKET_TAX,
    BUCKET_VAT_ADS,
    BUCKET_VAT_FEE_ACCOUNT,
    BUCKET_VAT_FEE_ORDER,
    PLATFORM_FEE_BUCKETS,
    StatementParseError,
    parse_statement_csv,
)

HEADER = 'Date,Type,Title,Info,Currency,Amount,"Fees & Taxes",Net,"Tax Details"'


def _csv(*rows: str) -> bytes:
    """Build a statement CSV. A BOM is prepended — real exports carry one."""
    return ("﻿" + "\n".join((HEADER, *rows)) + "\n").encode("utf-8")


def _parse(*rows: str):
    return parse_statement_csv(_csv(*rows), "synthetic.csv")


def _total(lines, buckets) -> Decimal:
    return -sum(l.net_signed for l in lines if l.bucket in buckets)


# ---------- 1. duplicate preservation (the load-bearing one) ----------


def test_byte_identical_rows_are_all_kept_and_all_counted():
    """Three identical $0.04 VAT rows are three separate charges = $0.12.

    A composite content hash over (date, type, title, info, amount) — the
    obvious idempotency key — collapses these into one and under-books the fee.
    They are kept apart by their position in the file, nothing else.
    """
    row = '"January 30, 2026",VAT,"VAT: auto-renew sold ",,USD,--,-$0.04,-$0.04,--'
    parsed = _parse(row, row, row)

    assert len(parsed.lines) == 3
    assert [l.row_index for l in parsed.lines] == [0, 1, 2]
    assert _total(parsed.lines, ACCOUNT_FEE_OVERHEAD_BUCKETS) == Decimal("0.12")


def test_duplicate_rows_are_distinguishable_only_by_row_index():
    row = '"June 1, 2026",Fee,"Listing fee","Listing #4347345198",USD,--,-$0.20,-$0.20,--'
    lines = _parse(row, row).lines

    identical = {
        (l.entry_date, l.entry_type, l.title, l.info, l.net_signed) for l in lines
    }
    assert len(identical) == 1, "fixture must be byte-identical to be meaningful"
    assert {l.row_index for l in lines} == {0, 1}


# ---------- 2. signed sums ----------


def test_credits_are_positive_and_reduce_the_fee():
    """A refunded fee is a POSITIVE row. Summed signed it cancels the charge;
    summed with abs() it would double it."""
    lines = _parse(
        '"April 22, 2026",Fee,"Processing fee","Order #4026053403",USD,--,-$2.47,-$2.47,--',
        '"April 22, 2026",Fee,"Credit for processing fee","Order #4026053403",USD,--,$2.47,$2.47,--',
    ).lines

    assert _total(lines, PLATFORM_FEE_BUCKETS) == Decimal("0.00")
    assert sum(abs(l.net_signed) for l in lines) == Decimal("4.94"), (
        "abs() would book 4.94 of cost where Etsy charged nothing"
    )


def test_refund_to_buyer_for_sales_tax_is_positive():
    lines = _parse(
        '"January 24, 2026",Tax,"Sales tax paid by buyer","Order #3900000001",USD,--,-$4.24,-$4.24,--',
        '"January 24, 2026",Tax,"Refund to buyer for sales tax","Order #3900000001",USD,--,$4.24,$4.24,--',
    ).lines

    assert all(l.bucket == BUCKET_TAX for l in lines)
    assert sum(l.net_signed for l in lines) == Decimal("0.00")


# ---------- 3. identifier forms ----------


@pytest.mark.parametrize(
    "row,expected_order,expected_listing",
    [
        # Info: "Order #N" — the common form (1,600 rows in the real files)
        (
            '"January 30, 2026",Fee,"Processing fee","Order #3963804467",USD,--,-$2.47,-$2.47,--',
            "3963804467",
            None,
        ),
        # Info: lowercase "order: N", no '#' — appears on VAT credit rows
        (
            '"January 26, 2026",VAT,"VAT: transaction credit","order: 3902046506",USD,--,$0.58,$0.58,--',
            "3902046506",
            None,
        ),
        # Title carries the order when Info is empty (Sale / Refund rows)
        (
            '"January 30, 2026",Sale,"Payment for Order #3963804467",,USD,$36.10,--,$36.10,--',
            "3963804467",
            None,
        ),
        (
            '"June 26, 2026",Refund,"Partial refund for Order #4088645829",,USD,-$32.24,--,-$32.24,--',
            "4088645829",
            None,
        ),
        # Info: "Listing #N" — a LISTING, never an order
        (
            '"January 12, 2026",Fee,"Listing fee","Listing #4343151753",USD,--,-$0.20,-$0.20,--',
            None,
            "4343151753",
        ),
        # Info: "renew sold auto credit: N" — also a LISTING despite looking
        # exactly like the lowercase order form. THE TRAP.
        (
            '"January 24, 2026",VAT,"VAT: renew sold auto credit","renew sold auto credit: 4349699409",USD,--,$0.04,$0.04,--',
            None,
            "4349699409",
        ),
        # Info: daily ad bill — carries digits but no identifier at all
        (
            '"January 31, 2026",Marketing,"Etsy Ads","Bill for click-throughs to your shop on Jan 30, 2026",USD,--,-$1.45,-$1.45,--',
            None,
            None,
        ),
        # Deposit: digits live in the Title, and none of them is an id
        (
            '"January 26, 2026",Deposit,"$61.28 sent to your Payoneer Wallet",,USD,--,--,--,--',
            None,
            None,
        ),
    ],
)
def test_every_identifier_form_present_in_the_real_statements(
    row, expected_order, expected_listing
):
    line = _parse(row).lines[0]
    assert line.order_external_id == expected_order
    assert line.listing_external_id == expected_listing


def test_renew_sold_auto_credit_is_never_read_as_an_order():
    """Regression for the form task.md did not carry.

    All three ids appearing in this shape across the six real statements are in
    the `Listing #` set and none is in the `Order #` set. Read as an order it
    degrades silently into a phantom 'unmatched order' — which looks exactly
    like normal operation.
    """
    line = _parse(
        '"April 22, 2026",VAT,"VAT: renew sold auto credit","renew sold auto credit: 4343151753",USD,--,$0.04,$0.04,--'
    ).lines[0]

    assert line.order_external_id is None
    assert line.listing_external_id == "4343151753"
    assert line.bucket == BUCKET_VAT_FEE_ACCOUNT


def test_unknown_info_identifier_aborts_rather_than_being_ignored():
    with pytest.raises(StatementParseError, match="matches no known identifier"):
        _parse(
            '"January 30, 2026",Fee,"Mystery fee","Invoice #99887766",USD,--,-$1.00,-$1.00,--'
        )


# ---------- 4. bucket routing ----------


@pytest.mark.parametrize(
    "row,expected_bucket",
    [
        (
            '"January 30, 2026",Sale,"Payment for Order #3963804467",,USD,$36.10,--,$36.10,--',
            BUCKET_SALE,
        ),
        (
            '"January 30, 2026",Tax,"Sales tax paid by buyer","Order #3963804467",USD,--,-$6.51,-$6.51,--',
            BUCKET_TAX,
        ),
        (
            '"January 30, 2026",Fee,"Processing fee","Order #3963804467",USD,--,-$2.47,-$2.47,--',
            BUCKET_FEE_ORDER,
        ),
        (
            '"January 12, 2026",Fee,"Listing fee","Listing #4343151753",USD,--,-$0.20,-$0.20,--',
            BUCKET_FEE_ACCOUNT,
        ),
        (
            '"January 30, 2026",VAT,"VAT: Processing Fee","Order #3963804467",USD,--,-$0.49,-$0.49,--',
            BUCKET_VAT_FEE_ORDER,
        ),
        (
            '"January 15, 2026",VAT,"VAT: auto-renew sold ",,USD,--,-$0.04,-$0.04,--',
            BUCKET_VAT_FEE_ACCOUNT,
        ),
        # VAT on advertising follows the line it taxes, into the ads bucket
        (
            '"January 31, 2026",VAT,"VAT: Etsy Ads",,USD,--,-$0.29,-$0.29,--',
            BUCKET_VAT_ADS,
        ),
        (
            '"January 30, 2026",VAT,"VAT: Offsite Ads fee","Order #3963804467",USD,--,-$0.89,-$0.89,--',
            BUCKET_VAT_ADS,
        ),
        (
            '"January 26, 2026",VAT,"VAT: Offsite Ads fee credit","order: 3902046506",USD,--,$1.59,$1.59,--',
            BUCKET_VAT_ADS,
        ),
        (
            '"January 30, 2026",Marketing,"Fee for sale made through Offsite Ads","Order #3963804467",USD,--,-$4.44,-$4.44,--',
            BUCKET_ADS_OFFSITE,
        ),
        (
            '"January 26, 2026",Marketing,"Credit for Offsite Ads fee","Order #3902046506",USD,--,$7.95,$7.95,--',
            BUCKET_ADS_OFFSITE,
        ),
        (
            '"January 31, 2026",Marketing,"Etsy Ads","Bill for click-throughs to your shop on Jan 30, 2026",USD,--,-$1.45,-$1.45,--',
            BUCKET_ADS_ETSY,
        ),
        (
            '"March 6, 2026",Marketing,"Credit for Etsy Ads",,USD,--,$3.23,$3.23,--',
            BUCKET_ADS_ETSY,
        ),
        (
            '"January 13, 2026","Buyer Fee","Colorado Retail Delivery Fee (paid by buyer)","Order #3942434022",USD,--,-$0.28,-$0.28,--',
            BUCKET_BUYER_FEE,
        ),
        (
            '"January 24, 2026",Refund,"Refund for Order #3902046506",,USD,-$57.23,--,-$57.23,--',
            BUCKET_REFUND,
        ),
        (
            '"January 26, 2026",Deposit,"$61.28 sent to your Payoneer Wallet",,USD,--,--,--,--',
            BUCKET_DEPOSIT,
        ),
    ],
)
def test_bucket_routing(row, expected_bucket):
    assert _parse(row).lines[0].bucket == expected_bucket


def test_credit_for_etsy_ads_is_not_dropped_by_an_equality_match():
    """`Title == "Etsy Ads"` silently drops this row — the named failure mode."""
    lines = _parse(
        '"March 5, 2026",Marketing,"Etsy Ads","Bill for click-throughs to your shop on Mar 4, 2026",USD,--,-$10.00,-$10.00,--',
        '"March 6, 2026",Marketing,"Credit for Etsy Ads",,USD,--,$3.48,$3.48,--',
    ).lines

    assert all(l.bucket in ADS_OVERHEAD_BUCKETS for l in lines)
    assert _total(lines, ADS_OVERHEAD_BUCKETS) == Decimal("6.52")


def test_offsite_ads_keeps_its_order_id_while_booking_to_overhead():
    """Rule 5: the ad spend goes to overhead, but per-order attribution stays
    queryable without re-parsing the file."""
    line = _parse(
        '"January 30, 2026",Marketing,"Fee for sale made through Offsite Ads","Order #3963804467",USD,--,-$4.44,-$4.44,--'
    ).lines[0]

    assert line.bucket in ADS_OVERHEAD_BUCKETS
    assert line.bucket not in PLATFORM_FEE_BUCKETS
    assert line.order_external_id == "3963804467"


def test_unknown_marketing_title_aborts():
    with pytest.raises(StatementParseError, match="neither the Offsite nor the Etsy Ads"):
        _parse(
            '"January 31, 2026",Marketing,"Sponsored placement pilot",,USD,--,-$5.00,-$5.00,--'
        )


def test_unknown_type_aborts():
    with pytest.raises(StatementParseError, match="unknown Type 'Chargeback'"):
        _parse(
            '"January 31, 2026",Chargeback,"Disputed order","Order #3963804467",USD,--,-$5.00,-$5.00,--'
        )


# ---------- 5. file-level invariants ----------


def test_non_usd_row_aborts_rather_than_converting():
    with pytest.raises(StatementParseError, match="is not USD"):
        _parse(
            '"January 30, 2026",Fee,"Processing fee","Order #3963804467",EUR,--,-$2.47,-$2.47,--'
        )


def test_period_is_derived_from_the_rows():
    parsed = _parse(
        '"April 30, 2026",Fee,"Processing fee","Order #4026053403",USD,--,-$2.47,-$2.47,--',
        '"April 1, 2026",Fee,"Listing fee","Listing #4343151753",USD,--,-$0.20,-$0.20,--',
    )
    assert parsed.period_month == date(2026, 4, 1)


def test_file_spanning_two_months_aborts():
    """The period is the import's idempotency key, so a file with no single
    period has no identity to replace."""
    with pytest.raises(StatementParseError, match="spans more than one calendar month"):
        _parse(
            '"April 30, 2026",Fee,"Processing fee","Order #4026053403",USD,--,-$2.47,-$2.47,--',
            '"May 1, 2026",Fee,"Processing fee","Order #4026053404",USD,--,-$2.47,-$2.47,--',
        )


def test_month_attribution_uses_the_charge_date_not_the_bill_date_in_info():
    """A Jan-1 row bills Dec-31 click-throughs. The real January statement
    contains exactly this row; attributing it by the Info date would move it into
    a period the file does not cover and break the reconciliation."""
    parsed = _parse(
        '"January 1, 2026",Marketing,"Etsy Ads","Bill for click-throughs to your shop on Dec 31, 2025",USD,--,-$1.63,-$1.63,--'
    )
    assert parsed.period_month == date(2026, 1, 1)
    assert parsed.lines[0].entry_date == date(2026, 1, 1)


def test_deposit_amount_is_lifted_from_the_title():
    """Etsy leaves every money column '--' on a payout. The amount is the best
    independent cross-check available, so the parser recovers it."""
    line = _parse(
        '"January 19, 2026",Deposit,"$325.20 sent to your Payoneer Wallet",,USD,--,--,--,--'
    ).lines[0]

    assert line.amount_signed == Decimal("325.20")
    assert line.net_signed == Decimal("0.00"), "a payout is not a cost"


def test_thousands_separator_is_parsed():
    line = _parse(
        '"May 19, 2026",Deposit,"$1,234.56 sent to your Payoneer Wallet",,USD,--,--,--,--'
    ).lines[0]
    assert line.amount_signed == Decimal("1234.56")


def test_net_equals_amount_plus_fees_taxes():
    """Holds on all 2,728 real rows; the aggregates rely on `net_signed` alone."""
    line = _parse(
        '"January 30, 2026",Sale,"Payment for Order #3963804467",,USD,$36.10,--,$36.10,--'
    ).lines[0]
    assert line.amount_signed == Decimal("36.10")
    assert line.fees_taxes_signed is None
    assert line.net_signed == Decimal("36.10")


def test_missing_column_aborts_with_the_header_it_found():
    bad = ("﻿" + "Date,Type,Title\n" + '"January 1, 2026",Fee,"x"\n').encode()
    with pytest.raises(StatementParseError, match="missing expected column"):
        parse_statement_csv(bad, "broken.csv")


def test_empty_file_aborts():
    with pytest.raises(StatementParseError, match="no data rows"):
        parse_statement_csv(("﻿" + HEADER + "\n").encode(), "empty.csv")


def test_file_hash_is_stable_and_content_addressed():
    a = parse_statement_csv(_csv('"January 1, 2026",Deposit,"$1.00 sent to your Payoneer Wallet",,USD,--,--,--,--'), "a.csv")
    b = parse_statement_csv(_csv('"January 1, 2026",Deposit,"$1.00 sent to your Payoneer Wallet",,USD,--,--,--,--'), "b.csv")
    c = parse_statement_csv(_csv('"January 1, 2026",Deposit,"$2.00 sent to your Payoneer Wallet",,USD,--,--,--,--'), "c.csv")

    assert a.file_sha256 == b.file_sha256
    assert a.file_sha256 != c.file_sha256


# ---------- the split, end to end on one synthetic month ----------


def test_the_three_buckets_partition_every_booked_row():
    """One order, priced the way a real offsite-attributed order is priced.

    Fee + fee-VAT reach the order; ads + ads-VAT and the listing fee + its VAT
    each go to their own overhead row. Nothing booked is left over.
    """
    parsed = _parse(
        '"April 10, 2026",Sale,"Payment for Order #4026053403",,USD,$40.00,--,$40.00,--',
        '"April 10, 2026",Tax,"Sales tax paid by buyer","Order #4026053403",USD,--,-$3.00,-$3.00,--',
        '"April 10, 2026",Fee,"Processing fee","Order #4026053403",USD,--,-$2.00,-$2.00,--',
        '"April 10, 2026",Fee,"Transaction fee: Shipping","Order #4026053403",USD,--,-$0.50,-$0.50,--',
        '"April 10, 2026",VAT,"VAT: transaction","Order #4026053403",USD,--,-$0.40,-$0.40,--',
        '"April 10, 2026",Marketing,"Fee for sale made through Offsite Ads","Order #4026053403",USD,--,-$5.00,-$5.00,--',
        '"April 10, 2026",VAT,"VAT: Offsite Ads fee","Order #4026053403",USD,--,-$1.00,-$1.00,--',
        '"April 11, 2026",Marketing,"Etsy Ads","Bill for click-throughs to your shop on Apr 10, 2026",USD,--,-$3.00,-$3.00,--',
        '"April 11, 2026",VAT,"VAT: Etsy Ads",,USD,--,-$0.60,-$0.60,--',
        '"April 12, 2026",Fee,"Listing fee","Listing #4343151753",USD,--,-$0.20,-$0.20,--',
        '"April 12, 2026",VAT,"VAT: auto-renew sold ",,USD,--,-$0.04,-$0.04,--',
    )
    lines = parsed.lines

    assert _total(lines, PLATFORM_FEE_BUCKETS) == Decimal("2.90")
    assert _total(lines, ADS_OVERHEAD_BUCKETS) == Decimal("9.60")
    assert _total(lines, ACCOUNT_FEE_OVERHEAD_BUCKETS) == Decimal("0.24")

    base = sum(l.amount_signed for l in lines if l.bucket == BUCKET_SALE) + sum(
        l.net_signed for l in lines if l.bucket == BUCKET_TAX
    )
    assert base == Decimal("37.00")

    booked = (
        PLATFORM_FEE_BUCKETS | ADS_OVERHEAD_BUCKETS | ACCOUNT_FEE_OVERHEAD_BUCKETS
    )
    unbooked = {l.bucket for l in lines} - booked
    assert unbooked == {BUCKET_SALE, BUCKET_TAX}, (
        "only Sale and Tax should be unbooked here — a new unbooked bucket means "
        "money is going nowhere"
    )
