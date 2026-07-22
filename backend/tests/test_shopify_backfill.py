"""SHOPIFY-BACKFILL — pagination, date-range, idempotency, throttle backoff,
and status mapping for the paginated Shopify sync.

Same mocking style as test_shopify_sync_catalog.py: AsyncMock + MagicMock, patch
the fetch seam with canned GraphQL page bodies. No real HTTP.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from models.order import Order, OrderStatus
from models.shop import ShopPlatform
from services.shopify_sync import (
    ShopifyThrottledError,
    _build_orders_query_filter,
    _count_items_without_sku,
    _fetch_orders_page,
    _line_item_sku,
    backfill_order_numbers,
    map_shopify_status,
    sync_shop_orders,
)


# ---------- helpers ----------


def _make_shop():
    shop = MagicMock()
    shop.id = uuid4()
    shop.name = "MyShop"
    shop.platform = ShopPlatform.SHOPIFY
    shop.shopify_store_url = "test.myshopify.com"
    shop.shopify_access_token_encrypted = b"encrypted"
    shop.last_synced_at = None
    return shop


def _make_db(*, existing_external_ids=None):
    existing = set(existing_external_ids or [])
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    async def execute(stmt):
        result = MagicMock()
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        if "external_id" in compiled:
            for ext_id in existing:
                if f"'{ext_id}'" in compiled:
                    result.scalar_one_or_none.return_value = MagicMock()
                    return result
        result.scalar_one_or_none.return_value = None
        return result

    db.execute = AsyncMock(side_effect=execute)
    return db


def _order_node(*, order_id, created_at="2026-03-15T10:00:00Z",
                fulfillment_status="UNFULFILLED", cancelled_at=None, closed_at=None,
                line_items=None):
    return {
        "node": {
            "id": f"gid://shopify/Order/{order_id}",
            "name": f"#{order_id}",
            "createdAt": created_at,
            "closedAt": closed_at,
            "cancelledAt": cancelled_at,
            "displayFinancialStatus": "PAID",
            "displayFulfillmentStatus": fulfillment_status,
            "totalPriceSet": {"shopMoney": {"amount": "100.00", "currencyCode": "USD"}},
            "note": None,
            "customer": {"firstName": "T", "lastName": "B", "email": "b@example.com"},
            "shippingAddress": {"name": "T B", "phone": None, "address1": None,
                                "address2": None, "city": None, "provinceCode": None,
                                "zip": None, "countryCodeV2": "US"},
            "lineItems": {"edges": line_items or []},
        }
    }


def _variant_line_item(*, sku, product_id=888, variant_id=999):
    """A line item backed by a Shopify variant + product (resolvable → has SKU)."""
    return {"node": {
        "title": "Leather Wallet",
        "quantity": 2,
        "originalUnitPriceSet": {"shopMoney": {"amount": "50.00", "currencyCode": "USD"}},
        "variant": {
            "id": f"gid://shopify/ProductVariant/{variant_id}",
            "sku": sku,
            "title": "Brown",
            "product": {"id": f"gid://shopify/Product/{product_id}", "title": "Wallet"},
            "inventoryItem": {"measurement": {"weight": {"value": 100, "unit": "GRAMS"}}},
        },
    }}


def _custom_line_item():
    """A line item with no variant (custom / personalised) → no resolvable SKU,
    hence no eventual link back to a BOM for cost."""
    return {"node": {
        "title": "Gift wrap",
        "quantity": 1,
        "originalUnitPriceSet": {"shopMoney": {"amount": "5.00", "currencyCode": "USD"}},
        "variant": None,
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


# ---------- status mapping ----------


@pytest.mark.parametrize("fulfillment,cancelled,expected", [
    (None, "2026-01-02T00:00:00Z", OrderStatus.CANCELLED),
    ("FULFILLED", "2026-01-02T00:00:00Z", OrderStatus.CANCELLED),  # cancel wins
    ("FULFILLED", None, OrderStatus.COMPLETED),
    ("PARTIALLY_FULFILLED", None, OrderStatus.IN_PRODUCTION),
    ("UNFULFILLED", None, OrderStatus.NEW),
    ("OPEN", None, OrderStatus.NEW),
    (None, None, OrderStatus.NEW),
])
def test_map_shopify_status(fulfillment, cancelled, expected):
    assert map_shopify_status(fulfillment, cancelled) == expected


# ---------- date-range query filter ----------


def test_build_query_filter_both_bounds():
    q = _build_orders_query_filter(date(2026, 1, 1), date(2026, 7, 21))
    assert q == "created_at:>=2026-01-01 created_at:<=2026-07-21"


def test_build_query_filter_since_only():
    assert _build_orders_query_filter(date(2026, 1, 1), None) == "created_at:>=2026-01-01"


def test_build_query_filter_none():
    assert _build_orders_query_filter(None, None) is None


@pytest.mark.asyncio
async def test_date_range_passed_to_shopify_query_var():
    shop = _make_shop()
    db = _make_db()
    fetch = AsyncMock(return_value=_page([]))
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page", fetch):
        await sync_shop_orders(db, shop, MagicMock(),
                               since=date(2026, 1, 1), until=date(2026, 7, 21),
                               dry_run=True, stop_on_existing=False)
    variables = fetch.await_args.args[2]
    assert variables["query"] == "created_at:>=2026-01-01 created_at:<=2026-07-21"


# ---------- multi-page pagination ----------


@pytest.mark.asyncio
async def test_pagination_walks_all_pages():
    shop = _make_shop()
    db = _make_db()
    pages = [
        _page([_order_node(order_id=1)], has_next=True, cursor="c1"),
        _page([_order_node(order_id=2)], has_next=True, cursor="c2"),
        _page([_order_node(order_id=3)], has_next=False),
    ]
    fetch = AsyncMock(side_effect=pages)
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page", fetch), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        result = await sync_shop_orders(db, shop, MagicMock(),
                                        stop_on_existing=False)
    assert fetch.await_count == 3
    assert result.imported == 3
    assert result.found == 3
    assert mock_create.await_count == 3
    # cursor threaded through: page 2 used c1, page 3 used c2
    assert fetch.await_args_list[1].args[2]["after"] == "c1"
    assert fetch.await_args_list[2].args[2]["after"] == "c2"


@pytest.mark.asyncio
async def test_stop_on_existing_halts_before_next_page():
    """Ongoing mode: a page containing an already-imported order is the catch-up
    boundary — do not fetch further pages even though hasNextPage is true."""
    shop = _make_shop()
    db = _make_db(existing_external_ids={"2"})
    pages = [
        _page([_order_node(order_id=1), _order_node(order_id=2)], has_next=True, cursor="c1"),
        _page([_order_node(order_id=3)], has_next=False),  # must NOT be reached
    ]
    fetch = AsyncMock(side_effect=pages)
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page", fetch), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        result = await sync_shop_orders(db, shop, MagicMock())  # stop_on_existing default True
    assert fetch.await_count == 1
    assert result.imported == 1   # order 1
    assert result.skipped == 1    # order 2 already present
    assert mock_create.await_count == 1


# ---------- idempotency ----------


@pytest.mark.asyncio
async def test_idempotent_second_run_creates_nothing():
    shop = _make_shop()
    edges = [_order_node(order_id=10), _order_node(order_id=11)]
    page = _page(edges)

    # Run 1: empty DB → both imported.
    db1 = _make_db()
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=page)), \
         patch("services.shopify_sync.create_order", AsyncMock()) as create1:
        r1 = await sync_shop_orders(db1, shop, MagicMock(), stop_on_existing=False)
    assert r1.imported == 2 and create1.await_count == 2

    # Run 2: same orders now present → zero new rows.
    db2 = _make_db(existing_external_ids={"10", "11"})
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=page)), \
         patch("services.shopify_sync.create_order", AsyncMock()) as create2:
        r2 = await sync_shop_orders(db2, shop, MagicMock(), stop_on_existing=False)
    assert r2.imported == 0
    assert r2.skipped == 2
    create2.assert_not_awaited()


# ---------- dry run ----------


@pytest.mark.asyncio
async def test_dry_run_writes_nothing_but_counts_by_month():
    shop = _make_shop()
    db = _make_db()
    page = _page([
        _order_node(order_id=20, created_at="2026-01-05T10:00:00Z"),
        _order_node(order_id=21, created_at="2026-02-05T10:00:00Z"),
    ])
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=page)), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        result = await sync_shop_orders(db, shop, MagicMock(),
                                        since=date(2026, 1, 1), dry_run=True,
                                        stop_on_existing=False)
    mock_create.assert_not_awaited()
    assert result.dry_run is True
    assert result.imported == 0
    assert result.found == 2
    assert result.would_create == 2
    assert result.by_month["2026-01"] == {"found": 1, "already_present": 0, "created": 1}
    assert result.by_month["2026-02"] == {"found": 1, "already_present": 0, "created": 1}
    # last_synced_at must NOT be stamped on a dry run
    assert shop.last_synced_at is None


# ---------- throttle backoff ----------


@pytest.mark.asyncio
async def test_fetch_orders_page_backs_off_on_throttle():
    """_fetch_orders_page retries a THROTTLED page after sleeping, then succeeds."""
    good = _page([])
    inner = AsyncMock(side_effect=[ShopifyThrottledError(2.5), good])
    sleep = AsyncMock()
    with patch("services.shopify_sync._post_orders_page", inner), \
         patch("services.shopify_sync.asyncio.sleep", sleep):
        result = await _fetch_orders_page("shop", "tok", {"first": 50})
    assert result is good
    assert inner.await_count == 2
    sleep.assert_awaited_once()
    assert sleep.await_args.args[0] == 2.5  # honoured the reported deficit


@pytest.mark.asyncio
async def test_fetch_orders_page_gives_up_after_max_retries():
    inner = AsyncMock(side_effect=ShopifyThrottledError(0.01))
    with patch("services.shopify_sync._post_orders_page", inner), \
         patch("services.shopify_sync.asyncio.sleep", AsyncMock()):
        with pytest.raises(ShopifyThrottledError):
            await _fetch_orders_page("shop", "tok", {"first": 50})


# ---------- backfill status is applied on the created order ----------


@pytest.mark.asyncio
async def test_fulfilled_order_imported_as_completed():
    shop = _make_shop()
    db = _make_db()
    page = _page([_order_node(order_id=30, fulfillment_status="FULFILLED",
                              closed_at="2026-03-20T00:00:00Z")])
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=page)), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        await sync_shop_orders(db, shop, MagicMock(), stop_on_existing=False)
    kwargs = mock_create.await_args.kwargs
    assert kwargs["status"] == OrderStatus.COMPLETED
    assert kwargs["completed_at"] is not None


# ---------- SKU snapshot retention (BOM link durability) ----------


def test_line_item_sku_resolution():
    """Pure helper: Shopify SKU wins; missing SKU → synthetic product/variant id;
    no variant/product → None (no usable SKU)."""
    assert _line_item_sku(_variant_line_item(sku="WALLET-BRN")["node"]) == "WALLET-BRN"
    # blank SKU but a real variant → synthetic, still a usable catalog link
    assert _line_item_sku(
        _variant_line_item(sku="  ", product_id=1, variant_id=2)["node"]
    ) == "shopify-1-2"
    assert _line_item_sku(_custom_line_item()["node"]) is None


@pytest.mark.asyncio
async def test_backfilled_item_retains_sku_snapshot():
    """A created order item carries the resolved SKU as a durable snapshot on the
    item itself (not only via product_variant_id, which is SET NULL on variant
    delete) — SKU is the only later link back to BOM/cost."""
    shop = _make_shop()
    db = _make_db()
    fake_variant = MagicMock()
    fake_variant.id = uuid4()
    page = _page([_order_node(order_id=40,
                              line_items=[_variant_line_item(sku="WALLET-BRN")])])
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=page)), \
         patch("services.shopify_sync.ensure_catalog_row",
               AsyncMock(return_value=fake_variant)), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        await sync_shop_orders(db, shop, MagicMock(), stop_on_existing=False)
    payload = mock_create.await_args.args[1]  # the OrderCreate passed to create_order
    assert payload.items[0].sku == "WALLET-BRN"
    assert payload.items[0].product_variant_id == fake_variant.id


# ---------- dry-run status breakdown + no-SKU count (Open Question 2) ----------


@pytest.mark.asyncio
async def test_dry_run_reports_status_breakdown():
    """The per-status breakdown reveals how many historical orders would land as
    NEW (flooding the active pipeline) vs terminal COMPLETED/CANCELLED."""
    shop = _make_shop()
    db = _make_db()
    page = _page([
        _order_node(order_id=50, fulfillment_status="FULFILLED"),            # COMPLETED
        _order_node(order_id=51, fulfillment_status="UNFULFILLED"),          # NEW
        _order_node(order_id=52, fulfillment_status="UNFULFILLED"),          # NEW
        _order_node(order_id=53, cancelled_at="2026-03-01T00:00:00Z"),       # CANCELLED
        _order_node(order_id=54, fulfillment_status="PARTIALLY_FULFILLED"),  # IN_PRODUCTION
    ])
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=page)), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        result = await sync_shop_orders(db, shop, MagicMock(),
                                        dry_run=True, stop_on_existing=False)
    mock_create.assert_not_awaited()
    assert result.by_status == {
        "completed": 1, "new": 2, "cancelled": 1, "in_production": 1,
    }


@pytest.mark.asyncio
async def test_dry_run_counts_items_without_usable_sku():
    """A line item with no resolvable variant (custom item) is counted as having
    no usable SKU — surfaced in the dry run before the import writes anything."""
    shop = _make_shop()
    db = _make_db()
    page = _page([
        _order_node(order_id=60, line_items=[
            _variant_line_item(sku="OK-1"),   # usable
            _custom_line_item(),              # NOT usable
        ]),
        _order_node(order_id=61, line_items=[_custom_line_item()]),  # NOT usable
    ])
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=page)), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        result = await sync_shop_orders(db, shop, MagicMock(),
                                        dry_run=True, stop_on_existing=False)
    mock_create.assert_not_awaited()
    assert result.items_without_sku == 2
    assert result.would_create == 2


@pytest.mark.asyncio
async def test_already_present_orders_excluded_from_status_and_sku_counts():
    """Skipped (already-imported) orders must not inflate by_status / no-SKU
    counts — those diagnostics describe only what the import would create."""
    shop = _make_shop()
    db = _make_db(existing_external_ids={"71"})
    page = _page([
        _order_node(order_id=70, line_items=[_custom_line_item()]),  # would create
        _order_node(order_id=71, line_items=[_custom_line_item()]),  # already present
    ])
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=page)), \
         patch("services.shopify_sync.create_order", AsyncMock()):
        result = await sync_shop_orders(db, shop, MagicMock(),
                                        dry_run=True, stop_on_existing=False)
    assert result.by_status == {"new": 1}   # only order 70
    assert result.items_without_sku == 1    # only order 70's custom item
    assert result.skipped == 1


# ---------- ORDER-CARD-1 Part 1: Shopify human order number ----------


@pytest.mark.asyncio
async def test_sync_captures_order_number():
    """The synced order carries the Shopify human `name` as order_number on the
    OrderCreate handed to create_order (not just as a title fallback)."""
    shop = _make_shop()
    db = _make_db()
    page = _page([_order_node(order_id=40)])  # _order_node sets name="#40"
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=page)), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        await sync_shop_orders(db, shop, MagicMock(), stop_on_existing=False)
    payload = mock_create.await_args.args[1]  # the OrderCreate passed to create_order
    assert payload.order_number == "#40"


def _make_backfill_db(missing_ids):
    """DB mock for backfill_order_numbers: the SELECT returns the external_ids
    still missing a number; each UPDATE reports one affected row."""
    db = MagicMock()
    db.flush = AsyncMock()

    async def execute(stmt):
        result = MagicMock()
        if str(stmt).strip().upper().startswith("SELECT"):
            scalars = MagicMock()
            scalars.all.return_value = list(missing_ids)
            result.scalars.return_value = scalars
            return result
        result.rowcount = 1  # UPDATE
        return result

    db.execute = AsyncMock(side_effect=execute)
    return db


@pytest.mark.asyncio
async def test_backfill_order_numbers_updates_existing_rows():
    """Backfill maps id → name from Shopify and UPDATEs matching rows; it never
    creates orders (the idempotent sync path is untouched)."""
    shop = _make_shop()
    db = _make_backfill_db(missing_ids=["40", "41"])
    page = _page([_order_node(order_id=40), _order_node(order_id=41)])
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=page)), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        result = await backfill_order_numbers(db, shop)
    mock_create.assert_not_awaited()
    assert result == {"updated": 2, "examined": 2}
    update_calls = [
        c for c in db.execute.await_args_list
        if str(c.args[0]).strip().upper().startswith("UPDATE")
    ]
    assert len(update_calls) == 2


@pytest.mark.asyncio
async def test_backfill_order_numbers_noop_when_none_missing():
    """Idempotent: with no NULL order_number rows, no Shopify call is made."""
    shop = _make_shop()
    db = _make_backfill_db(missing_ids=[])
    fetch = AsyncMock(return_value=_page([]))
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", fetch):
        result = await backfill_order_numbers(db, shop)
    fetch.assert_not_awaited()
    assert result == {"updated": 0, "examined": 0}


@pytest.mark.asyncio
async def test_backfill_order_numbers_skips_non_shopify():
    shop = _make_shop()
    shop.platform = ShopPlatform.ETSY
    result = await backfill_order_numbers(MagicMock(), shop)
    assert result == {"updated": 0, "examined": 0}
