"""STATEMENT-IMPORT — import service regression guards.

Covers what the parser cannot: the DB-facing behaviour that makes the import
safe to run twice, and the derivation of `order.platform_fee` as an AGGREGATE
over accumulated lines rather than a blind write.

Session style: an in-memory fake that actually stores the lines it is given and
answers the service's queries from that store, so replace-by-period and
cross-period aggregation are exercised for real rather than stubbed. The two
predicates that would silently corrupt other data if they drifted — the DELETE's
scoping and the fee aggregate's bucket filter — are additionally asserted
against the compiled SQL, as elsewhere in this suite.

All fixtures are synthetic; real statements never enter the repo.
"""

import re
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.sql.dml import Delete

from models.etsy_statement_line import EtsyStatementLine
from models.material import OverheadMaterial, OverheadMaterialReceipt
from models.order import Order
from models.shop import ShopPlatform
from services.etsy_statement_parser import (
    ACCOUNT_FEE_OVERHEAD_BUCKETS,
    ADS_OVERHEAD_BUCKETS,
    BUCKET_SALE,
    PLATFORM_FEE_BUCKETS,
)
from services.etsy_statement_service import (
    ACCOUNT_FEE_OVERHEAD_MATERIAL,
    ADS_OVERHEAD_MATERIAL,
    import_statement,
)

HEADER = 'Date,Type,Title,Info,Currency,Amount,"Fees & Taxes",Net,"Tax Details"'
_DATE_LITERAL = re.compile(r"'(\d{4}-\d{2}-\d{2})'")
# literal_binds renders a UUID as bare hex, without dashes.
_UUID_LITERAL = re.compile(r"'([0-9a-f]{32})'")


def _uuids_in(sql: str) -> set[str]:
    return set(_UUID_LITERAL.findall(sql))


def _csv(*rows: str) -> bytes:
    return ("﻿" + "\n".join((HEADER, *rows)) + "\n").encode("utf-8")


def _shop():
    shop = MagicMock()
    shop.id = uuid.uuid4()
    shop.platform = ShopPlatform.ETSY
    return shop


def _order(external_id: str, platform_fee=None) -> Order:
    return Order(
        id=uuid.uuid4(),
        external_id=external_id,
        shop_id=None,
        platform_fee=platform_fee,
    )


class FakeSession:
    """Minimal async session backed by python lists.

    Implements only the query shapes `etsy_statement_service` issues, dispatched
    on `column_descriptions` (each shape is distinguishable). Filtering mirrors
    the service's intended semantics; the WHERE clauses themselves are asserted
    separately from the compiled SQL.
    """

    def __init__(self, orders: list[Order]):
        self.lines: list[EtsyStatementLine] = []
        self.orders = {o.external_id: o for o in orders}
        self.orders_by_id = {o.id: o for o in orders}
        self.receipts: list[OverheadMaterialReceipt] = []
        self.materials: list[OverheadMaterial] = []
        self.compiled: list[str] = []
        self.flush = AsyncMock()
        # A dry run's rollback is the caller-visible proof that it wrote nothing;
        # this fake records it rather than undoing, so a test can assert both the
        # rollback AND that the report was built from real accumulated state.
        self.rollback = AsyncMock()
        self.commit = AsyncMock()

    # -- writes ------------------------------------------------------------
    def add(self, obj):
        if isinstance(obj, EtsyStatementLine):
            self.lines.append(obj)
        elif isinstance(obj, OverheadMaterialReceipt):
            self.receipts.append(obj)
        elif isinstance(obj, OverheadMaterial):
            obj.id = uuid.uuid4()
            self.materials.append(obj)

    async def delete(self, obj):
        if isinstance(obj, OverheadMaterialReceipt):
            self.receipts.remove(obj)

    # -- reads -------------------------------------------------------------
    async def execute(self, stmt):
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        self.compiled.append(sql)

        if isinstance(stmt, Delete):
            period = _DATE_LITERAL.search(sql).group(1)
            self.lines = [
                l for l in self.lines if str(l.period_month) != period
            ]
            return _Result()

        cols = tuple(d.get("name") for d in stmt.column_descriptions)

        if cols == ("Order",):
            if "external_id IN" in sql:
                wanted = set(re.findall(r"'(\d+)'", sql))
                return _Result(
                    scalars=[
                        o for k, o in self.orders.items() if k in wanted
                    ]
                )
            wanted_ids = _uuids_in(sql)
            return _Result(
                scalars=[
                    o
                    for oid, o in self.orders_by_id.items()
                    if oid.hex in wanted_ids
                ]
            )

        if cols == ("EtsyStatementLine",):
            period = _DATE_LITERAL.search(sql).group(1)
            return _Result(
                scalars=[l for l in self.lines if str(l.period_month) == period]
            )

        if cols == ("id", "platform_fee"):
            wanted_ids = _uuids_in(sql)
            return _Result(
                rows=[
                    (o.id, o.platform_fee)
                    for oid, o in self.orders_by_id.items()
                    if oid.hex in wanted_ids
                ]
            )

        if cols == ("order_id", "sum"):
            wanted_ids = _uuids_in(sql)
            totals: dict[uuid.UUID, Decimal] = {}
            for l in self.lines:
                if l.order_id is None or l.order_id.hex not in wanted_ids:
                    continue
                if l.bucket not in PLATFORM_FEE_BUCKETS:
                    continue
                totals[l.order_id] = totals.get(l.order_id, Decimal("0")) + l.net_signed
            return _Result(rows=list(totals.items()))

        if cols == ("order_external_id",):
            wanted = set(re.findall(r"'(\d+)'", sql))
            return _Result(
                rows=[
                    (l.order_external_id,)
                    for l in self.lines
                    if l.order_external_id in wanted and l.bucket == BUCKET_SALE
                ]
            )

        if cols == ("order_id",):
            wanted_ids = _uuids_in(sql)
            return _Result(
                rows=[
                    (l.order_id,)
                    for l in self.lines
                    if l.order_id is not None
                    and l.order_id.hex in wanted_ids
                    and l.bucket == BUCKET_SALE
                ]
            )

        if cols == ("coalesce", "count"):
            period = _DATE_LITERAL.search(sql).group(1)
            buckets = (
                ADS_OVERHEAD_BUCKETS
                if "'ads_etsy'" in sql
                else ACCOUNT_FEE_OVERHEAD_BUCKETS
            )
            hit = [
                l
                for l in self.lines
                if str(l.period_month) == period and l.bucket in buckets
            ]
            return _Result(
                one=(sum((l.net_signed for l in hit), Decimal("0")), len(hit))
            )

        if cols == ("OverheadMaterialReceipt",):
            ref = re.search(r"'(etsy-stmt:[^']+)'", sql).group(1)
            found = [r for r in self.receipts if r.source_ref == ref]
            return _Result(scalars=found)

        if cols == ("OverheadMaterial",):
            name = re.search(r"name = '([^']*)'", sql).group(1)
            return _Result(scalars=[m for m in self.materials if m.name == name])

        raise AssertionError(f"FakeSession got an unhandled statement: {cols} :: {sql}")

    # -- helpers for assertions -------------------------------------------
    def receipt(self, scope: str) -> OverheadMaterialReceipt | None:
        for r in self.receipts:
            if r.source_ref and r.source_ref.endswith(f":{scope}"):
                return r
        return None

    @property
    def deletes(self) -> list[str]:
        return [s for s in self.compiled if s.lstrip().upper().startswith("DELETE")]


class _Result:
    def __init__(self, scalars=None, rows=None, one=None):
        self._scalars = scalars or []
        self._rows = rows if rows is not None else []
        self._one = one

    def scalars(self):
        return list(self._scalars)

    def scalar_one_or_none(self):
        return self._scalars[0] if self._scalars else None

    def one(self):
        return self._one

    def __iter__(self):
        return iter(self._rows)


async def _run(db, shop, *rows, filename="statement.csv", dry_run=False):
    """Default `dry_run=False` here, opposite the service's own default: these
    tests are about what a real import writes. The dry-run contract has its own
    tests below."""
    return await import_statement(
        db, shop, _csv(*rows), filename, uuid.uuid4(), dry_run=dry_run
    )


# ---------- fee derivation ----------

APRIL_ORDER = "4026053403"

APRIL_ROWS = (
    f'"April 10, 2026",Sale,"Payment for Order #{APRIL_ORDER}",,USD,$40.00,--,$40.00,--',
    f'"April 10, 2026",Tax,"Sales tax paid by buyer","Order #{APRIL_ORDER}",USD,--,-$3.00,-$3.00,--',
    f'"April 10, 2026",Fee,"Processing fee","Order #{APRIL_ORDER}",USD,--,-$2.00,-$2.00,--',
    f'"April 10, 2026",VAT,"VAT: transaction","Order #{APRIL_ORDER}",USD,--,-$0.40,-$0.40,--',
    f'"April 10, 2026",Marketing,"Fee for sale made through Offsite Ads","Order #{APRIL_ORDER}",USD,--,-$5.00,-$5.00,--',
    f'"April 10, 2026",VAT,"VAT: Offsite Ads fee","Order #{APRIL_ORDER}",USD,--,-$1.00,-$1.00,--',
    '"April 11, 2026",Marketing,"Etsy Ads","Bill for click-throughs to your shop on Apr 10, 2026",USD,--,-$3.00,-$3.00,--',
    '"April 11, 2026",VAT,"VAT: Etsy Ads",,USD,--,-$0.60,-$0.60,--',
    '"April 12, 2026",Fee,"Listing fee","Listing #4343151753",USD,--,-$0.20,-$0.20,--',
)


@pytest.mark.asyncio
async def test_platform_fee_is_the_signed_sum_of_fee_and_fee_vat_rows_only():
    """Advertising does NOT reach the order — that is the whole accounting
    split. $2.00 fee + $0.40 fee-VAT = $2.40, while $6.00 of offsite ad spend on
    the same order goes to overhead."""
    order = _order(APRIL_ORDER)
    db = FakeSession([order])

    report = await _run(db, _shop(), *APRIL_ROWS)

    assert order.platform_fee == Decimal("2.40")
    assert report.orders_matched == 1
    assert report.ads_overhead_amount == Decimal("9.60")
    assert report.account_fee_overhead_amount == Decimal("0.20")
    assert report.statement_base_amount == Decimal("37.00")


@pytest.mark.asyncio
async def test_fee_credits_net_against_the_charge():
    order = _order(APRIL_ORDER)
    db = FakeSession([order])

    await _run(
        db,
        _shop(),
        f'"April 10, 2026",Fee,"Processing fee","Order #{APRIL_ORDER}",USD,--,-$2.47,-$2.47,--',
        f'"April 22, 2026",Fee,"Credit for processing fee","Order #{APRIL_ORDER}",USD,--,$2.37,$2.37,--',
    )

    assert order.platform_fee == Decimal("0.10")


@pytest.mark.asyncio
async def test_order_with_no_fee_lines_left_goes_to_null_not_zero():
    """NULL means 'not priced' and keeps other pricing paths open; 0.00 would
    assert Etsy charged nothing, which is a different and untrue claim."""
    order = _order(APRIL_ORDER, platform_fee=Decimal("2.40"))
    db = FakeSession([order])

    await _run(db, _shop(), *APRIL_ROWS)
    assert order.platform_fee == Decimal("2.40")

    # Re-issued April with the fee lines removed entirely.
    await _run(
        db,
        _shop_same(db),
        f'"April 10, 2026",Sale,"Payment for Order #{APRIL_ORDER}",,USD,$40.00,--,$40.00,--',
    )
    assert order.platform_fee is None


def _shop_same(db):
    """The same shop id the first import used (read back off a stored line)."""
    shop = MagicMock()
    shop.id = db.lines[0].shop_id if db.lines else uuid.uuid4()
    shop.platform = ShopPlatform.ETSY
    return shop


# ---------- idempotency ----------


@pytest.mark.asyncio
async def test_reimporting_the_same_file_is_a_no_op():
    """The whole point of replace-by-period: lines do not accumulate, the fee
    does not move, and no second overhead row appears."""
    order = _order(APRIL_ORDER)
    db = FakeSession([order])
    shop = _shop()

    first = await _run(db, shop, *APRIL_ROWS)
    lines_after_first = len(db.lines)
    receipts_after_first = len(db.receipts)

    second = await _run(db, shop, *APRIL_ROWS)

    assert len(db.lines) == lines_after_first
    assert len(db.receipts) == receipts_after_first == 2
    assert order.platform_fee == Decimal("2.40")
    assert second.lines_replaced == first.lines_imported
    assert second.identical_file is True
    assert second.fee_overrides == [], "a repeat import must report no overrides"


@pytest.mark.asyncio
async def test_duplicate_rows_survive_the_round_trip_into_storage():
    """The parser keeps them (see test_etsy_statement_parser); this proves the
    service stores all of them rather than collapsing on the way in."""
    order = _order(APRIL_ORDER)
    db = FakeSession([order])
    dup = '"April 12, 2026",VAT,"VAT: auto-renew sold ",,USD,--,-$0.04,-$0.04,--'

    report = await _run(db, _shop(), dup, dup, dup)

    assert len(db.lines) == 3
    assert report.account_fee_overhead_amount == Decimal("0.12")
    assert db.receipt("account-fees").total_cost == Decimal("0.12")


@pytest.mark.asyncio
async def test_reissued_statement_supersedes_the_original_period():
    """Rows that disappeared from a re-issue must actually be gone — the
    behaviour an upsert-only key could never provide."""
    order = _order(APRIL_ORDER)
    db = FakeSession([order])
    shop = _shop()

    await _run(db, shop, *APRIL_ROWS)
    assert order.platform_fee == Decimal("2.40")

    await _run(
        db,
        shop,
        f'"April 10, 2026",Fee,"Processing fee","Order #{APRIL_ORDER}",USD,--,-$1.00,-$1.00,--',
    )

    assert len(db.lines) == 1
    assert order.platform_fee == Decimal("1.00")
    assert db.receipt("ads") is None, "the re-issue has no ad rows, so the row goes"


@pytest.mark.asyncio
async def test_delete_is_scoped_to_this_shop_and_period():
    db = FakeSession([_order(APRIL_ORDER)])
    shop = _shop()

    await _run(db, shop, *APRIL_ROWS)

    sql = db.deletes[0]
    assert shop.id.hex in sql
    assert "2026-04-01" in sql
    assert "period_month" in sql and "shop_id" in sql


# ---------- cross-period aggregation ----------


@pytest.mark.asyncio
async def test_a_later_period_credit_updates_the_earlier_order_by_exactly_that_credit():
    """Statements overlap. The fee is recomputed from ALL accumulated lines, so
    a May credit against an April order moves that order and nothing else."""
    order = _order(APRIL_ORDER)
    db = FakeSession([order])
    shop = _shop()

    await _run(db, shop, *APRIL_ROWS)
    assert order.platform_fee == Decimal("2.40")

    report = await _run(
        db,
        shop,
        f'"May 3, 2026",Fee,"Credit for processing fee","Order #{APRIL_ORDER}",USD,--,$0.50,$0.50,--',
    )

    assert order.platform_fee == Decimal("1.90")
    assert report.period == "2026-05"
    assert any(
        o.order_external_id == APRIL_ORDER
        and o.previous_platform_fee == Decimal("2.40")
        and o.statement_platform_fee == Decimal("1.90")
        for o in report.fee_overrides
    )


@pytest.mark.asyncio
async def test_fee_aggregate_only_sums_the_platform_fee_buckets():
    db = FakeSession([_order(APRIL_ORDER)])
    await _run(db, _shop(), *APRIL_ROWS)

    aggregate = next(s for s in db.compiled if "sum(" in s.lower() and "group by" in s.lower())
    assert "'fee_order'" in aggregate and "'vat_fee_order'" in aggregate
    assert "'ads_offsite'" not in aggregate and "'vat_ads'" not in aggregate


# ---------- unmatched + overrides + credit-only ----------


@pytest.mark.asyncio
async def test_unmatched_order_is_counted_and_reported_never_created():
    db = FakeSession([])  # this shop has no such order

    report = await _run(
        db,
        _shop(),
        '"April 10, 2026",Fee,"Processing fee","Order #9999999999",USD,--,-$2.00,-$2.00,--',
        '"April 10, 2026",VAT,"VAT: transaction","Order #9999999999",USD,--,-$0.40,-$0.40,--',
    )

    assert report.orders_matched == 0
    assert report.orders_unmatched == 1
    assert report.unmatched_orders[0].order_external_id == "9999999999"
    assert report.unmatched_orders[0].platform_fee_amount == Decimal("2.40")
    assert len(db.lines) == 2, "the lines are still stored, just unlinked"
    assert all(l.order_id is None for l in db.lines)


@pytest.mark.asyncio
async def test_unmatched_entries_say_whether_the_statement_sold_that_id():
    """The signal that separates "OrderHub is missing this order" from "this is
    not an order number at all". Both render as a number and an amount without
    it."""
    db = FakeSession([])

    report = await _run(
        db,
        _shop(),
        # Sold in this very file -> a real Etsy order, absent from OrderHub.
        '"April 10, 2026",Sale,"Payment for Order #4026053403",,USD,$40.00,--,$40.00,--',
        '"April 10, 2026",Fee,"Processing fee","Order #4026053403",USD,--,-$2.00,-$2.00,--',
        # No Sale row anywhere -> could be a mis-extracted id. Worth a look.
        '"April 12, 2026",Fee,"Processing fee","Order #9999999999",USD,--,-$1.00,-$1.00,--',
    )

    flags = {u.order_external_id: u.has_sale_row for u in report.unmatched_orders}
    assert flags == {"4026053403": True, "9999999999": False}


@pytest.mark.asyncio
async def test_a_sale_row_from_an_earlier_period_still_counts():
    """The query runs over every period stored for the shop, not just this file —
    an order sold in April and charged a fee credit in May is one Etsy order, and
    the May report must say so."""
    db = FakeSession([])
    shop = _shop()

    await _run(
        db,
        shop,
        '"April 10, 2026",Sale,"Payment for Order #4026053403",,USD,$40.00,--,$40.00,--',
    )
    report = await _run(
        db,
        shop,
        '"May 03, 2026",Fee,"Processing fee credit","Order #4026053403",USD,--,$0.50,$0.50,--',
    )

    assert [u.has_sale_row for u in report.unmatched_orders] == [True]


@pytest.mark.asyncio
async def test_a_listing_id_never_reaches_the_unmatched_list_at_all():
    """Defence in depth for the same failure. The parser reads
    `renew sold auto credit: N` as a LISTING id, so it never becomes an unmatched
    order — and if it ever did, it would carry has_sale_row=False, because listing
    ids and sale ids are disjoint sets."""
    db = FakeSession([])

    report = await _run(
        db,
        _shop(),
        '"April 12, 2026",Fee,"Auto-renew sold fee","renew sold auto credit: 4343151753",USD,--,-$0.20,-$0.20,--',
    )

    assert report.unmatched_orders == []
    assert db.lines[0].listing_external_id == "4343151753"
    assert db.lines[0].order_external_id is None


@pytest.mark.asyncio
async def test_statement_overrides_a_hand_entered_fee_and_reports_it():
    """Rule 6 — and deliberately the OPPOSITE of SHOP-FEE-1's flat-rate rule,
    where a manual fee is never overwritten. The statement is what Etsy actually
    charged, so it wins; the override is reported, never silent."""
    order = _order(APRIL_ORDER, platform_fee=Decimal("5.00"))
    db = FakeSession([order])

    report = await _run(db, _shop(), *APRIL_ROWS)

    assert order.platform_fee == Decimal("2.40")
    assert len(report.fee_overrides) == 1
    override = report.fee_overrides[0]
    assert override.order_external_id == APRIL_ORDER
    assert override.previous_platform_fee == Decimal("5.00")
    assert override.statement_platform_fee == Decimal("2.40")


@pytest.mark.asyncio
async def test_credit_only_order_keeps_its_negative_fee_and_is_flagged():
    """An order sold in a period we have NOT imported, refunded in one we have:
    only credits appear, so the signed fee is negative. Stored honestly (it
    self-corrects when the earlier month is loaded) and surfaced so the operator
    can decide to load it."""
    order = _order("3902046506")
    db = FakeSession([order])

    report = await _run(
        db,
        _shop(),
        '"January 24, 2026",Fee,"Credit for processing fee","Order #3902046506",USD,--,$3.73,$3.73,--',
        '"January 26, 2026",VAT,"VAT: transaction credit","order: 3902046506",USD,--,$0.58,$0.58,--',
    )

    assert order.platform_fee == Decimal("-4.31")
    assert len(report.credit_only_orders) == 1
    assert report.credit_only_orders[0].order_external_id == "3902046506"
    assert report.credit_only_orders[0].platform_fee_amount == Decimal("-4.31")


@pytest.mark.asyncio
async def test_a_refunded_order_with_its_own_sale_row_is_not_flagged_credit_only():
    order = _order(APRIL_ORDER)
    db = FakeSession([order])

    report = await _run(
        db,
        _shop(),
        f'"April 10, 2026",Sale,"Payment for Order #{APRIL_ORDER}",,USD,$40.00,--,$40.00,--',
        f'"April 10, 2026",Fee,"Processing fee","Order #{APRIL_ORDER}",USD,--,-$2.00,-$2.00,--',
        f'"April 22, 2026",Fee,"Credit for processing fee","Order #{APRIL_ORDER}",USD,--,$2.50,$2.50,--',
    )

    assert order.platform_fee == Decimal("-0.50")
    assert report.credit_only_orders == []


# ---------- overhead rows ----------


@pytest.mark.asyncio
async def test_two_overhead_rows_one_per_shop_per_month():
    db = FakeSession([_order(APRIL_ORDER)])
    shop = _shop()

    await _run(db, shop, *APRIL_ROWS)

    ads = db.receipt("ads")
    account = db.receipt("account-fees")
    assert ads is not None and account is not None
    assert ads.source_ref == "etsy-stmt:2026-04:ads"
    assert account.source_ref == "etsy-stmt:2026-04:account-fees"
    assert ads.total_cost == Decimal("9.60")
    assert account.total_cost == Decimal("0.20")
    assert ads.shop_id == shop.id
    assert ads.currency == "USD"
    # Month-end, so it buckets into the month the statement covers.
    assert ads.received_at.date() == date(2026, 4, 30)

    names = {m.name for m in db.materials}
    assert names == {ADS_OVERHEAD_MATERIAL, ACCOUNT_FEE_OVERHEAD_MATERIAL}


@pytest.mark.asyncio
async def test_reimport_updates_the_overhead_row_rather_than_appending():
    db = FakeSession([_order(APRIL_ORDER)])
    shop = _shop()

    await _run(db, shop, *APRIL_ROWS)
    await _run(
        db,
        shop,
        '"April 11, 2026",Marketing,"Etsy Ads","Bill for click-throughs to your shop on Apr 10, 2026",USD,--,-$7.00,-$7.00,--',
    )

    ads_rows = [r for r in db.receipts if r.source_ref == "etsy-stmt:2026-04:ads"]
    assert len(ads_rows) == 1
    assert ads_rows[0].total_cost == Decimal("7.00")


@pytest.mark.asyncio
async def test_a_credit_heavy_month_books_a_negative_overhead_row():
    """More ad credits than charges is rare but real. The REST create schema
    forbids `total_cost < 0`, which is why this service writes through the ORM —
    clamping would misstate the month."""
    db = FakeSession([])

    report = await _run(
        db,
        _shop(),
        '"March 5, 2026",Marketing,"Etsy Ads","Bill for click-throughs to your shop on Mar 4, 2026",USD,--,-$1.00,-$1.00,--',
        '"March 6, 2026",Marketing,"Credit for Etsy Ads",,USD,--,$3.48,$3.48,--',
    )

    assert report.ads_overhead_amount == Decimal("-2.48")
    assert db.receipt("ads").total_cost == Decimal("-2.48")


@pytest.mark.asyncio
async def test_existing_overhead_material_is_reused_not_duplicated():
    db = FakeSession([_order(APRIL_ORDER)])
    existing = OverheadMaterial(name=ADS_OVERHEAD_MATERIAL, unit="month", is_active=True)
    existing.id = uuid.uuid4()
    db.materials.append(existing)

    await _run(db, _shop(), *APRIL_ROWS)

    ads_materials = [m for m in db.materials if m.name == ADS_OVERHEAD_MATERIAL]
    assert len(ads_materials) == 1
    assert db.receipt("ads").overhead_material_id == existing.id


# ---------- report cross-checks ----------


@pytest.mark.asyncio
async def test_report_carries_the_deposit_and_refund_cross_checks():
    db = FakeSession([])

    report = await _run(
        db,
        _shop(),
        '"January 24, 2026",Refund,"Refund for Order #3902046506",,USD,-$57.23,--,-$57.23,--',
        '"January 26, 2026",Deposit,"$61.28 sent to your Payoneer Wallet",,USD,--,--,--,--',
        '"January 19, 2026",Deposit,"$325.20 sent to your Payoneer Wallet",,USD,--,--,--,--',
    )

    assert report.refunds_count == 1
    assert report.refunds_amount == Decimal("-57.23")
    assert report.deposits_count == 2
    assert report.deposits_amount == Decimal("386.48")
    # Neither touches the booked buckets.
    assert report.ads_overhead_amount == Decimal("0.00")
    assert report.account_fee_overhead_amount == Decimal("0.00")


@pytest.mark.asyncio
async def test_refund_rows_do_not_move_the_fee_or_the_overhead():
    """Rule 8 sanity: leaving Refund rows unbooked cannot distort either bucket.
    Fee credits reach the order through their own Fee/VAT rows, which is correct
    and separate."""
    order = _order(APRIL_ORDER)
    db = FakeSession([order])

    with_refund = await _run(
        db,
        _shop(),
        *APRIL_ROWS,
        f'"April 22, 2026",Refund,"Refund for Order #{APRIL_ORDER}",,USD,-$40.00,--,-$40.00,--',
    )

    assert order.platform_fee == Decimal("2.40")
    assert with_refund.ads_overhead_amount == Decimal("9.60")
    assert with_refund.refunds_count == 1


# ---------- dry run ----------


@pytest.mark.asyncio
async def test_dry_run_report_is_identical_to_the_real_import():
    """The load-bearing property. A rehearsal that can disagree with the
    performance is worse than none, so the dry run is not a second derivation —
    it is the same code path, rolled back. Only `dry_run` itself may differ."""
    rows = (
        *APRIL_ROWS,
        '"April 15, 2026",Fee,"Processing fee","Order #9999999999",USD,--,-$1.11,-$1.11,--',
    )

    rehearsal = FakeSession([_order(APRIL_ORDER, platform_fee=Decimal("5.00"))])
    dry = await _run(rehearsal, _shop(), *rows, dry_run=True)

    # A fresh session, because the real import must start from the same state the
    # rehearsal started from — which is exactly what the rollback guarantees.
    performance = FakeSession([_order(APRIL_ORDER, platform_fee=Decimal("5.00"))])
    real = await _run(performance, _shop(), *rows, dry_run=False)

    assert dry.dry_run is True
    assert real.dry_run is False
    assert dry.model_dump(exclude={"dry_run"}) == real.model_dump(exclude={"dry_run"})


@pytest.mark.asyncio
async def test_dry_run_rolls_back_and_never_commits():
    db = FakeSession([_order(APRIL_ORDER)])

    await _run(db, _shop(), *APRIL_ROWS, dry_run=True)

    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_real_import_does_not_roll_itself_back():
    db = FakeSession([_order(APRIL_ORDER)])

    await _run(db, _shop(), *APRIL_ROWS, dry_run=False)

    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_service_default_is_a_rehearsal():
    """Mirrors SHOP-FEE-1: a caller that forgets the flag must not write."""
    db = FakeSession([_order(APRIL_ORDER)])

    report = await import_statement(
        db, _shop(), _csv(*APRIL_ROWS), "statement.csv", uuid.uuid4()
    )

    assert report.dry_run is True
    db.rollback.assert_awaited_once()
