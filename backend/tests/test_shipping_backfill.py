"""ORDER-SHIPPING-1 — backfilling shipping/discount/tax onto existing orders.

The sync dedups on (external_id, shop_id) and never revisits a row, and the
orders/updated webhook no-ops on one, so the mappers price NEW orders only. This
is the path that reaches everything already imported, and the properties that
matter are:

  - FILL-ONLY. The all-NULL guard is repeated in the UPDATE, not just the SELECT,
    so a re-run is a strict no-op and a value written between the two is never
    clobbered.
  - DRIFT IS REPORTED, NEVER WRITTEN. Where Shopify now disagrees with a stored
    value the run says so and moves on. Includes total_price drift, which is the
    first measurement of BUG-4.
  - THE REPORT RECONCILES. Per-month buckets are in the SHOP's timezone, because
    they are read against Shopify analytics, which reports in that timezone.
  - DRY RUN WRITES NOTHING but reports what a real run would do.

Mock-session style, as in test_platform_fee_backfill.py: statements are compiled
to strings so the predicate itself is under test, and the Shopify fetch seam is
patched with canned pages.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from models.shop import ShopPlatform
from services.shopify_sync import backfill_shipping_breakdown


# ---------- helpers ----------


def _make_shop(platform=ShopPlatform.SHOPIFY, creds=True):
    shop = MagicMock()
    shop.id = uuid4()
    shop.name = "Lamamarka"
    shop.platform = platform
    shop.shopify_store_url = "test.myshopify.com" if creds else None
    shop.shopify_access_token_encrypted = b"enc" if creds else None
    return shop


def _row(external_id, *, total_price="49.50", currency="USD",
         shipping=None, discount=None, tax=None):
    row = MagicMock()
    row.external_id = external_id
    row.currency = currency
    row.total_price = Decimal(total_price)
    row.shipping_revenue = shipping
    row.discount_total = discount
    row.tax_total = tax
    return row


def _node(external_id, *, name="91890_1841", amount="49.50", subtotal="40.50",
          shipping="9.00", discount="4.49", tax="0.00",
          created="2026-07-30T02:44:55Z", unit="44.99", qty=1):
    return {"node": {
        "id": f"gid://shopify/Order/{external_id}",
        "name": name,
        "createdAt": created,
        "totalPriceSet": {"shopMoney": {"amount": amount, "currencyCode": "USD"}},
        "subtotalPriceSet": {"shopMoney": {"amount": subtotal}},
        "totalShippingPriceSet": {"shopMoney": {"amount": shipping}},
        "totalDiscountsSet": {"shopMoney": {"amount": discount}},
        "totalTaxSet": {"shopMoney": {"amount": tax}},
        "lineItems": {"edges": [{"node": {
            "title": "Money Clip",
            "quantity": qty,
            "originalUnitPriceSet": {"shopMoney": {"amount": unit}},
            "variant": None,
        }}]},
    }}


def _page(edges, *, has_next=False, cursor=None):
    return {
        "data": {"orders": {
            "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
            "edges": edges,
        }},
        "extensions": {"cost": {"requestedQueryCost": 10, "throttleStatus": {
            "maximumAvailable": 1000.0, "currentlyAvailable": 990, "restoreRate": 50.0}}},
    }


def _make_db(rows, *, rowcount=1):
    db = MagicMock()
    db.flush = AsyncMock()
    db.compiled = []

    async def execute(stmt):
        db.compiled.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        result = MagicMock()
        result.all.return_value = rows
        result.rowcount = rowcount
        return result

    db.execute = AsyncMock(side_effect=execute)
    return db


def _selects(db):
    return [s for s in db.compiled if s.lstrip().upper().startswith("SELECT")]


def _updates(db):
    return [s for s in db.compiled if s.lstrip().upper().startswith("UPDATE")]


async def _run(shop, rows, pages, **kwargs):
    db = _make_db(rows)
    fetch = AsyncMock(side_effect=list(pages))
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", fetch):
        summary = await backfill_shipping_breakdown(db, shop, **kwargs)
    return db, summary, fetch


# ---------- guards ----------


@pytest.mark.asyncio
async def test_non_shopify_shop_is_a_no_op():
    db, summary, _ = await _run(_make_shop(platform=ShopPlatform.ETSY), [], [])
    assert summary["matched"] == 0
    assert summary["updated"] == 0
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_credentials_is_a_no_op():
    _, summary, _ = await _run(_make_shop(creds=False), [], [])
    assert summary["matched"] == 0


@pytest.mark.asyncio
async def test_no_orders_never_calls_shopify():
    """No point spending a GraphQL page budget on an empty shop."""
    _, summary, fetch = await _run(_make_shop(), [], [])
    assert summary["matched"] == 0
    fetch.assert_not_awaited()


# ---------- fill-only ----------


@pytest.mark.asyncio
async def test_writes_the_breakdown_onto_a_null_row():
    _, summary, _ = await _run(
        _make_shop(), [_row("7410546344092")], [_page([_node("7410546344092")])],
        dry_run=False,
    )
    assert summary["targets"] == 1
    assert summary["updated"] == 1


@pytest.mark.asyncio
async def test_update_repeats_the_all_null_guard():
    """The guard lives in the SELECT and AGAIN in the UPDATE. Without the second
    one, a value written between the two would be silently overwritten — and a
    re-run would stop being a no-op."""
    db, _, _ = await _run(
        _make_shop(), [_row("7410546344092")], [_page([_node("7410546344092")])],
        dry_run=False,
    )
    sql = _updates(db)[0].lower()
    assert "shipping_revenue is null" in sql
    assert "discount_total is null" in sql
    assert "tax_total is null" in sql


@pytest.mark.asyncio
async def test_a_populated_row_is_never_rewritten():
    """Re-running is a strict no-op: a row that already carries the figures is
    not a target, so no UPDATE is even issued for it."""
    db, summary, _ = await _run(
        _make_shop(),
        [_row("7410546344092", shipping=Decimal("9.00"),
              discount=Decimal("4.49"), tax=Decimal("0.00"))],
        [_page([_node("7410546344092")])],
        dry_run=False,
    )
    assert summary["targets"] == 0
    assert summary["updated"] == 0
    assert _updates(db) == []


@pytest.mark.asyncio
async def test_a_partially_populated_row_is_not_a_target():
    """The three are written as a set. A row carrying only one of them is not a
    clean slate, and filling the gaps would mix figures from two runs."""
    _, summary, _ = await _run(
        _make_shop(),
        [_row("7410546344092", shipping=Decimal("9.00"))],
        [_page([_node("7410546344092")])],
        dry_run=False,
    )
    assert summary["targets"] == 0


# ---------- drift: reported, never written ----------


@pytest.mark.asyncio
async def test_reports_drift_without_writing_it():
    """A post-hoc discount in Shopify is real, but silently moving an order the
    operator has already reconciled is not this endpoint's call."""
    db, summary, _ = await _run(
        _make_shop(),
        [_row("7410546344092", shipping=Decimal("5.00"),
              discount=Decimal("4.49"), tax=Decimal("0.00"))],
        [_page([_node("7410546344092")])],  # Shopify now says 9.00
        dry_run=False,
    )
    assert summary["drift"]["shipping_revenue"] == 1
    assert summary["updated"] == 0
    assert _updates(db) == []
    sample = next(s for s in summary["drift_samples"] if s["field"] == "shipping_revenue")
    assert sample["stored"] == 5.0
    assert sample["shopify"] == 9.0


@pytest.mark.asyncio
async def test_reports_total_price_drift_as_bug4_evidence():
    """BUG-4 is 'orders list reads a stale total_price'. This run is the first
    thing that ever compares the stored total against Shopify's, so it measures
    the exposure — and, per the sprint's scope, changes nothing."""
    db, summary, _ = await _run(
        _make_shop(),
        [_row("7410546344092", total_price="40.00")],  # Shopify says 49.50
        [_page([_node("7410546344092")])],
        dry_run=False,
    )
    assert summary["drift"]["total_price"] == 1
    # Measured, not corrected: the UPDATE never mentions total_price at all.
    assert "total_price" not in _updates(db)[0].lower()


@pytest.mark.asyncio
async def test_no_drift_when_shopify_agrees():
    _, summary, _ = await _run(
        _make_shop(),
        [_row("7410546344092", shipping=Decimal("9.00"),
              discount=Decimal("4.49"), tax=Decimal("0.00"))],
        [_page([_node("7410546344092")])],
    )
    assert summary["drift"] == {
        "shipping_revenue": 0, "discount_total": 0, "tax_total": 0, "total_price": 0,
    }


# ---------- dry run ----------


@pytest.mark.asyncio
async def test_dry_run_writes_nothing_but_reports_the_impact():
    db, summary, _ = await _run(
        _make_shop(), [_row("7410546344092")], [_page([_node("7410546344092")])],
    )
    assert summary["dry_run"] is True
    assert summary["updated"] == 0
    assert _updates(db) == []
    # ...yet the operator still sees exactly what a real run would do.
    assert summary["targets"] == 1
    assert summary["shipping_total_by_currency"] == {"USD": 9.0}


@pytest.mark.asyncio
async def test_dry_run_defaults_true():
    """A real write must be an explicit dry_run=false, like every other shop
    backfill."""
    _, summary, _ = await _run(
        _make_shop(), [_row("7410546344092")], [_page([_node("7410546344092")])],
    )
    assert summary["dry_run"] is True


# ---------- reconciliation figures ----------


@pytest.mark.asyncio
async def test_totals_are_per_currency():
    _, summary, _ = await _run(
        _make_shop(),
        [_row("1"), _row("2")],
        [_page([_node("1"), _node("2", name="91890_1842")])],
    )
    assert summary["shipping_total_by_currency"] == {"USD": 18.0}
    assert summary["discount_total_by_currency"] == {"USD": 8.98}


@pytest.mark.asyncio
async def test_months_bucket_in_the_shop_timezone_not_utc():
    """The report is read against Shopify analytics, which reports in the shop's
    timezone. SHOPIFY-REFUNDS-followup-2 recorded what bucketing the same money
    in UTC costs: 2024-12 came out $39.99 wrong.

    2026-04-30T22:30:00Z is 2026-05-01 01:30 in Kyiv (UTC+3 in summer), so this
    order belongs to MAY in every figure Shopify will show the operator.
    """
    _, summary, _ = await _run(
        _make_shop(), [_row("1")],
        [_page([_node("1", created="2026-04-30T22:30:00Z")])],
    )
    assert "2026-05" in summary["by_month"]
    assert "2026-04" not in summary["by_month"]


@pytest.mark.asyncio
async def test_month_buckets_carry_the_three_figures():
    _, summary, _ = await _run(
        _make_shop(), [_row("1")], [_page([_node("1")])],
    )
    bucket = summary["by_month"]["2026-07"]
    assert bucket == {"orders": 1, "shipping": 9.0, "discount": 4.49, "tax": 0.0}


@pytest.mark.asyncio
async def test_totals_include_rows_that_are_not_write_targets():
    """The reconciliation covers the whole window, not just the part this run
    happens to fill — otherwise a second run would report a smaller total than
    the first and neither would tie to Shopify."""
    _, summary, _ = await _run(
        _make_shop(),
        [_row("1", shipping=Decimal("9.00"), discount=Decimal("4.49"),
              tax=Decimal("0.00"))],
        [_page([_node("1")])],
    )
    assert summary["targets"] == 0
    assert summary["shipping_total_by_currency"] == {"USD": 9.0}


@pytest.mark.asyncio
async def test_reports_unbalanced_orders():
    _, summary, _ = await _run(
        _make_shop(), [_row("1")],
        [_page([_node("1", subtotal="35.00")])],  # 35 + 9 + 0 != 49.50
    )
    assert summary["unbalanced"] == [
        {"order_number": "91890_1841", "external_id": "1", "reason": "shopify"}
    ]


@pytest.mark.asyncio
async def test_an_order_missing_from_shopify_stays_null():
    """Deleted upstream, or outside the page filter. Its columns stay NULL, which
    reads correctly as 'unknown' — inventing a 0.00 would be the defect this
    sprint removes."""
    _, summary, _ = await _run(
        _make_shop(), [_row("1"), _row("gone")], [_page([_node("1")])],
        dry_run=False,
    )
    assert summary["found_in_shopify"] == 1
    assert summary["missing_in_shopify"] == 1
    assert summary["targets"] == 1


# ---------- windowing ----------


@pytest.mark.asyncio
async def test_window_bounds_on_ordered_at_not_the_finance_expression():
    """backfill_platform_fees windows by COALESCE(shipped_at, ordered_at) because
    it bounds what it re-prices in the P&L. This one is compared against Shopify's
    order feed, so it has to select the same orders the Shopify-side `created_at`
    page filter does — a different expression would put the two ends of the
    reconciliation on different clocks."""
    db, _, _ = await _run(
        _make_shop(), [_row("1")], [_page([_node("1")])],
        since=date(2026, 7, 1), until=date(2026, 7, 31),
    )
    sql = _selects(db)[0].lower()
    assert "ordered_at" in sql
    assert "coalesce" not in sql
    assert "2026-07-01" in sql and "2026-07-31" in sql


@pytest.mark.asyncio
async def test_window_is_passed_to_the_shopify_page_filter_too():
    _, _, fetch = await _run(
        _make_shop(), [_row("1")], [_page([_node("1")])],
        since=date(2026, 7, 1),
    )
    variables = fetch.await_args.args[2]
    assert "created_at:>=2026-07-01" in variables["query"]


# ---------- paging ----------


@pytest.mark.asyncio
async def test_pages_until_every_target_is_found():
    """Same shape as backfill_order_numbers: walk pages, stop as soon as the
    remaining set empties, at ~1 GraphQL call per 50 orders."""
    _, summary, fetch = await _run(
        _make_shop(), [_row("1"), _row("2")],
        [
            _page([_node("1")], has_next=True, cursor="cur1"),
            _page([_node("2", name="91890_1842")]),
        ],
    )
    assert fetch.await_count == 2
    assert summary["found_in_shopify"] == 2
    # Second call resumed from the first page's cursor.
    assert fetch.await_args_list[1].args[2]["after"] == "cur1"


@pytest.mark.asyncio
async def test_stops_paging_once_nothing_remains():
    """A shop with 831 Shopify orders but 2 in the window must not walk all 17
    pages."""
    _, _, fetch = await _run(
        _make_shop(), [_row("1")],
        [_page([_node("1")], has_next=True, cursor="cur1")],
    )
    assert fetch.await_count == 1


# ---------- the router surface ----------
#
# Router functions are awaited directly with mock sessions, matching
# test_shop_fee_router.py. The OWNER role dependency itself is declarative and is
# covered by test_route_scope_completeness.

from datetime import datetime, timezone  # noqa: E402

from fastapi import HTTPException  # noqa: E402

from models.shop import Shop  # noqa: E402
from models.user import UserRole  # noqa: E402
from routers.shops import backfill_shop_shipping  # noqa: E402
from schemas.shop import ShopShippingBackfillRequest  # noqa: E402


def _orm_shop(platform=ShopPlatform.SHOPIFY, creds=True):
    now = datetime.now(timezone.utc)
    shop = Shop(
        id=uuid4(),
        name="Lamamarka",
        platform=platform,
        color="#6366F1",
        is_active=True,
        np_default_weight_kg=0.5,
        np_default_volume_m3=0.004,
        np_default_payer_type="Sender",
        np_default_payment_method="Cash",
        last_synced_at=None,
        shopify_store_url="test.myshopify.com" if creds else None,
        shopify_access_token_encrypted=b"enc" if creds else None,
    )
    shop.created_at = now
    shop.updated_at = now
    return shop


def _owner():
    u = MagicMock()
    u.role = UserRole.OWNER
    u.id = uuid4()
    return u


def _db_returning_shop(shop):
    db = MagicMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = shop
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_route_404_for_unknown_shop():
    with pytest.raises(HTTPException) as exc:
        await backfill_shop_shipping(
            uuid4(), ShopShippingBackfillRequest(),
            current_user=_owner(), db=_db_returning_shop(None),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_route_422_for_a_non_shopify_shop():
    """422 rather than a silent no-op: Etsy and manual orders have no channel
    figures to capture, and the operator asking for one deserves to be told."""
    with pytest.raises(HTTPException) as exc:
        await backfill_shop_shipping(
            uuid4(), ShopShippingBackfillRequest(),
            current_user=_owner(),
            db=_db_returning_shop(_orm_shop(platform=ShopPlatform.ETSY)),
        )
    assert exc.value.status_code == 422
    assert "Shopify" in exc.value.detail


@pytest.mark.asyncio
async def test_route_422_without_credentials():
    with pytest.raises(HTTPException) as exc:
        await backfill_shop_shipping(
            uuid4(), ShopShippingBackfillRequest(),
            current_user=_owner(),
            db=_db_returning_shop(_orm_shop(creds=False)),
        )
    assert exc.value.status_code == 422
    assert "credentials" in exc.value.detail


@pytest.mark.asyncio
async def test_route_dry_run_rolls_back():
    """Belt and braces: the service already skips the UPDATE, and the router
    rolls back on top, so a dry run cannot persist anything by any route."""
    db = _db_returning_shop(_orm_shop())
    with patch("routers.shops.backfill_shipping_breakdown",
               AsyncMock(return_value={"matched": 3, "updated": 0, "dry_run": True})):
        out = await backfill_shop_shipping(
            uuid4(), ShopShippingBackfillRequest(dry_run=True),
            current_user=_owner(), db=db,
        )
    db.rollback.assert_awaited_once()
    assert out["status"] == "success"
    assert out["dry_run"] is True


@pytest.mark.asyncio
async def test_route_real_run_does_not_roll_back():
    db = _db_returning_shop(_orm_shop())
    with patch("routers.shops.backfill_shipping_breakdown",
               AsyncMock(return_value={"matched": 3, "updated": 3, "dry_run": False})):
        await backfill_shop_shipping(
            uuid4(), ShopShippingBackfillRequest(dry_run=False),
            current_user=_owner(), db=db,
        )
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_passes_the_window_through():
    db = _db_returning_shop(_orm_shop())
    with patch("routers.shops.backfill_shipping_breakdown",
               AsyncMock(return_value={"dry_run": True})) as mock_backfill:
        await backfill_shop_shipping(
            uuid4(),
            ShopShippingBackfillRequest(
                since=date(2026, 7, 1), until=date(2026, 7, 31), dry_run=True,
            ),
            current_user=_owner(), db=db,
        )
    kwargs = mock_backfill.await_args.kwargs
    assert kwargs["since"] == date(2026, 7, 1)
    assert kwargs["until"] == date(2026, 7, 31)
    assert kwargs["dry_run"] is True


def test_request_rejects_an_inverted_range():
    with pytest.raises(ValueError):
        ShopShippingBackfillRequest(since=date(2026, 7, 31), until=date(2026, 7, 1))


def test_request_dry_run_defaults_true():
    assert ShopShippingBackfillRequest().dry_run is True
