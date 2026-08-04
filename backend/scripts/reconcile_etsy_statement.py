"""OrderHub CRM — Etsy statement reconciliation harness (STATEMENT-IMPORT).

Parses a directory of Etsy payment-account statement CSVs and prints the
per-month accounting split the importer will produce, so the parser can be
proved against the real files without touching the database.

DATA HANDLING. The statements are financial + PII data and live OUTSIDE the
repo (`/mnt/g/lama.marka/ETSY/statement/`). This script reads them in place and
writes nothing; its output is not committed. No baseline figures are hardcoded
here either — pass `--expect` a local JSON file if you want a hard gate. That
keeps real revenue and fee totals out of git while still making the check
repeatable.

WHAT IT VERIFIES

Always, with no external baseline needed (exit 1 on any failure):
  - every row classifies into exactly one bucket, and the booked buckets plus
    the deliberately-unbooked ones (sale/tax/deposit/buyer_fee/refund) partition
    the file — money cannot silently go nowhere;
  - the three booked buckets sum to the all-in cost;
  - each file covers exactly one calendar month.

Optionally, against `--expect` (exit 1 on any drift):
  - per-month and grand-total base / platform_fee / ads / account-fee / all-in.

Usage:
  cd backend && python scripts/reconcile_etsy_statement.py /mnt/g/lama.marka/ETSY/statement/
  cd backend && python scripts/reconcile_etsy_statement.py <dir> --expect ~/baseline.json

`--expect` JSON shape (amounts as strings, to stay exact):
  {"2026-04": {"base": "949.69", "platform_fee": "153.60", "ads": "145.56",
               "account_fees": "7.30", "orders": 24},
   "grand":   {"base": "8016.94", ...}}
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.etsy_statement_parser import (  # noqa: E402
    ACCOUNT_FEE_OVERHEAD_BUCKETS,
    ADS_OVERHEAD_BUCKETS,
    BUCKET_BUYER_FEE,
    BUCKET_DEPOSIT,
    BUCKET_REFUND,
    BUCKET_SALE,
    BUCKET_TAX,
    PLATFORM_FEE_BUCKETS,
    StatementParseError,
    parse_statement_csv,
)

ZERO = Decimal("0.00")

#: Buckets deliberately not booked to a fee or an overhead row. Sale and Tax
#: establish the base; Deposit is the payout cross-check; Buyer Fee is
#: buyer-paid; Refund revenue handling is a separate sprint.
UNBOOKED_BUCKETS = frozenset(
    {BUCKET_SALE, BUCKET_TAX, BUCKET_DEPOSIT, BUCKET_BUYER_FEE, BUCKET_REFUND}
)


def _booked(lines, buckets) -> Decimal:
    """Cost, as a positive number: statement rows carry costs as negatives."""
    return -sum((l.net_signed for l in lines if l.bucket in buckets), ZERO)


def summarise(lines) -> dict:
    sales = [l for l in lines if l.bucket == BUCKET_SALE]
    base = sum((l.amount_signed or ZERO) for l in sales) + sum(
        (l.net_signed for l in lines if l.bucket == BUCKET_TAX), ZERO
    )
    return {
        "orders": len(sales),
        "base": Decimal(base),
        "platform_fee": _booked(lines, PLATFORM_FEE_BUCKETS),
        "ads": _booked(lines, ADS_OVERHEAD_BUCKETS),
        "account_fees": _booked(lines, ACCOUNT_FEE_OVERHEAD_BUCKETS),
        "deposits": sum(
            (l.amount_signed or ZERO) for l in lines if l.bucket == BUCKET_DEPOSIT
        ),
        "refunds": sum(
            (l.amount_signed or ZERO) for l in lines if l.bucket == BUCKET_REFUND
        ),
        "lines": len(lines),
    }


def check_partition(period: str, lines, failures: list[str]) -> None:
    booked = (
        PLATFORM_FEE_BUCKETS | ADS_OVERHEAD_BUCKETS | ACCOUNT_FEE_OVERHEAD_BUCKETS
    )
    known = booked | UNBOOKED_BUCKETS
    stray = {l.bucket for l in lines} - known
    if stray:
        failures.append(
            f"{period}: bucket(s) {sorted(stray)} are neither booked nor "
            "deliberately unbooked — money is going nowhere"
        )

    total = sum((l.net_signed for l in lines if l.bucket in booked), ZERO)
    parts = (
        _booked(lines, PLATFORM_FEE_BUCKETS)
        + _booked(lines, ADS_OVERHEAD_BUCKETS)
        + _booked(lines, ACCOUNT_FEE_OVERHEAD_BUCKETS)
    )
    if -total != parts:
        failures.append(
            f"{period}: the three booked buckets sum to {parts} but the booked "
            f"rows total {-total}"
        )


def compare(period: str, actual: dict, expected: dict, failures: list[str]) -> None:
    for key, want in expected.items():
        got = actual.get(key)
        if got is None:
            failures.append(f"{period}: baseline names unknown field {key!r}")
            continue
        want_value = Decimal(str(want)) if key != "orders" else int(want)
        if got != want_value:
            failures.append(
                f"{period}: {key} = {got}, baseline says {want_value} "
                f"(drift {Decimal(str(got)) - Decimal(str(want_value))})"
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("directory", type=Path, help="Directory of statement CSVs")
    ap.add_argument(
        "--expect",
        type=Path,
        default=None,
        help="Local JSON baseline to gate against (never commit it)",
    )
    args = ap.parse_args()

    paths = sorted(args.directory.glob("*.csv"))
    if not paths:
        print(f"No CSV files found in {args.directory}", file=sys.stderr)
        return 1

    failures: list[str] = []
    per_period: dict[str, dict] = {}

    for path in paths:
        try:
            parsed = parse_statement_csv(path.read_bytes(), path.name)
        except StatementParseError as exc:
            failures.append(f"{path.name}: {exc}")
            continue
        period = f"{parsed.period_month:%Y-%m}"
        if period in per_period:
            failures.append(f"{period}: covered by more than one file")
        check_partition(period, parsed.lines, failures)
        per_period[period] = summarise(parsed.lines)

    grand = {
        "orders": sum(v["orders"] for v in per_period.values()),
        "lines": sum(v["lines"] for v in per_period.values()),
    }
    for key in ("base", "platform_fee", "ads", "account_fees", "deposits", "refunds"):
        grand[key] = sum((v[key] for v in per_period.values()), ZERO)

    header = (
        f"{'Period':>8} {'Rows':>6} {'Orders':>7} {'Base':>10} "
        f"{'PlatformFee':>12} {'Ads':>10} {'AcctFees':>9} {'All-in':>10} {'Eff':>7}"
    )
    print(header)
    print("-" * len(header))
    for period in sorted(per_period):
        v = per_period[period]
        allin = v["platform_fee"] + v["ads"] + v["account_fees"]
        eff = f"{allin / v['base'] * 100:.2f}%" if v["base"] else "n/a"
        print(
            f"{period:>8} {v['lines']:>6} {v['orders']:>7} {v['base']:>10} "
            f"{v['platform_fee']:>12} {v['ads']:>10} {v['account_fees']:>9} "
            f"{allin:>10} {eff:>7}"
        )
    allin = grand["platform_fee"] + grand["ads"] + grand["account_fees"]
    eff = f"{allin / grand['base'] * 100:.2f}%" if grand["base"] else "n/a"
    print("-" * len(header))
    print(
        f"{'GRAND':>8} {grand['lines']:>6} {grand['orders']:>7} {grand['base']:>10} "
        f"{grand['platform_fee']:>12} {grand['ads']:>10} {grand['account_fees']:>9} "
        f"{allin:>10} {eff:>7}"
    )
    print(
        f"\nPayout cross-check: deposits {grand['deposits']} "
        f"vs booked activity {allin} (difference is settlement timing)."
    )
    print(f"Refunds parsed but not booked: {grand['refunds']}")

    if args.expect:
        baseline = json.loads(args.expect.read_text())
        for period, expected in baseline.items():
            actual = grand if period == "grand" else per_period.get(period)
            if actual is None:
                failures.append(f"{period}: baseline expects it, no file covers it")
                continue
            compare(period, actual, expected, failures)

    if failures:
        print("\nFAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("\nOK — all structural invariants hold" + (
        " and the baseline matches." if args.expect else "."
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
