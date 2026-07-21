"""IMP-2 — Shopify sync auto-creates Products/Variants and ingests line items.

Mirrors test_etsy_parser_catalog.py's mocking style: AsyncMock + MagicMock,
patch services.shopify_sync._fetch_orders_page with canned GraphQL payloads.
No real HTTP. Verifies the helper integration end-to-end through sync_shop_orders.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from models.order import Order, OrderItem
from models.product import Product, ProductVariant
from models.shop import ShopPlatform
from schemas.common import ImportResult
from services.catalog_import import _weight_to_grams
from services.shopify_sync import _parse_shopify_gid, sync_shop_orders


# ---------- _parse_shopify_gid ----------


def test_parse_shopify_gid_standard():
    assert _parse_shopify_gid("gid://shopify/Product/12345") == "12345"
    assert _parse_shopify_gid("gid://shopify/ProductVariant/98765") == "98765"
    assert _parse_shopify_gid("gid://shopify/Order/1") == "1"


def test_parse_shopify_gid_bare_id():
    assert _parse_shopify_gid("12345") == "12345"


def test_parse_shopify_gid_empty_or_none():
    assert _parse_shopify_gid("") == ""
    assert _parse_shopify_gid(None) == ""


# ---------- _weight_to_grams ----------


@pytest.mark.parametrize("unit,value,expected", [
    ("GRAMS", 250, 250),
    ("GRAMS", 1.5, 2),  # rounded
    ("KILOGRAMS", 1.5, 1500),
    ("KILOGRAMS", 0.25, 250),
    ("OUNCES", 4, 113),  # 4 * 28.3495 = 113.398
    ("POUNDS", 1, 454),  # 453.592 rounded
    ("POUNDS", 2.5, 1134),
])
def test_weight_to_grams_per_unit(unit, value, expected):
    assert _weight_to_grams({"value": value, "unit": unit}) == expected


def test_weight_to_grams_null_returns_zero():
    assert _weight_to_grams(None) == 0
    assert _weight_to_grams({}) == 0
    assert _weight_to_grams({"value": None, "unit": "GRAMS"}) == 0


def test_weight_to_grams_unknown_unit_returns_zero():
    assert _weight_to_grams({"value": 100, "unit": "STONES"}) == 0
    assert _weight_to_grams({"value": 100, "unit": None}) == 0


def test_weight_to_grams_invalid_value_returns_zero():
    assert _weight_to_grams({"value": "not-a-number", "unit": "GRAMS"}) == 0


# ---------- sync_shop_orders integration helpers ----------


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
    """A db mock whose .execute() returns a result whose scalar_one_or_none()
    matches a fake Order iff `external_id` was in `existing_external_ids` at the
    time of the call. Tracks added objects via .add."""
    existing = set(existing_external_ids or [])
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    async def execute(stmt):
        result = MagicMock()
        # Inspect the WHERE clause for an external_id literal — crude but enough
        # for our test queries (all `select(Order).where(external_id == X, ...)`).
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        if "external_id" in compiled:
            for ext_id in existing:
                if f"'{ext_id}'" in compiled:
                    fake_order = MagicMock()
                    result.scalar_one_or_none.return_value = fake_order
                    return result
        result.scalar_one_or_none.return_value = None
        return result

    db.execute = AsyncMock(side_effect=execute)
    return db


def _make_catalog_service(*, existing_product=None, taken_skus=None):
    taken = set(taken_skus or [])
    svc = MagicMock()
    svc.find_product_by_external_ref = AsyncMock(return_value=existing_product)
    svc.is_sku_taken = AsyncMock(side_effect=lambda shop_id, sku: sku in taken)
    return svc


def _line_item(*, title, quantity, price, sku, product_gid, variant_gid,
               variant_title="Default Title", weight=None, currency="USD"):
    return {
        "node": {
            "title": title,
            "quantity": quantity,
            "originalUnitPriceSet": {
                "shopMoney": {"amount": str(price), "currencyCode": currency}
            },
            "variant": {
                "id": variant_gid,
                "sku": sku,
                "title": variant_title,
                "product": {"id": product_gid, "title": title},
                "inventoryItem": {
                    "measurement": {"weight": weight}
                },
            },
        }
    }


def _order_node(*, order_gid, name, line_items, customer_email="buyer@example.com",
                created_at="2026-05-01T10:00:00Z", fulfillment_status="UNFULFILLED",
                financial_status="PAID", cancelled_at=None, closed_at=None):
    return {
        "node": {
            "id": order_gid,
            "name": name,
            "createdAt": created_at,
            "closedAt": closed_at,
            "cancelledAt": cancelled_at,
            "displayFinancialStatus": financial_status,
            "displayFulfillmentStatus": fulfillment_status,
            "totalPriceSet": {"shopMoney": {"amount": "100.00", "currencyCode": "USD"}},
            "note": None,
            "customer": {"firstName": "Test", "lastName": "Buyer", "email": customer_email},
            "shippingAddress": {
                "name": "Test Buyer", "phone": "+1234",
                "address1": "1 Test St", "address2": None, "city": "NYC",
                "provinceCode": "NY", "zip": "10001", "countryCodeV2": "US",
            },
            "lineItems": {"edges": line_items},
        }
    }


def _graphql_payload(orders, *, has_next_page=False, end_cursor=None):
    """Full-response shape returned by _fetch_orders_page: data + pageInfo (+ the
    extensions.cost block is optional; sync only reads it for proactive backoff)."""
    return {
        "data": {
            "orders": {
                "pageInfo": {"hasNextPage": has_next_page, "endCursor": end_cursor},
                "edges": orders,
            }
        },
        "extensions": {
            "cost": {
                "requestedQueryCost": 10,
                "throttleStatus": {
                    "maximumAvailable": 1000.0,
                    "currentlyAvailable": 990,
                    "restoreRate": 50.0,
                },
            }
        },
    }


# ---------- sync_shop_orders cases ----------


@pytest.mark.asyncio
async def test_fresh_sync_creates_products_and_variants():
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    user = MagicMock()
    user.id = uuid4()

    payload = _graphql_payload([
        _order_node(
            order_gid="gid://shopify/Order/1001",
            name="#1001",
            line_items=[
                _line_item(title="Wallet", quantity=1, price="49.99",
                           sku="WAL-001",
                           product_gid="gid://shopify/Product/100",
                           variant_gid="gid://shopify/ProductVariant/200",
                           weight={"value": 250, "unit": "GRAMS"}),
            ],
        ),
        _order_node(
            order_gid="gid://shopify/Order/1002",
            name="#1002",
            line_items=[
                _line_item(title="Belt", quantity=2, price="29.00",
                           sku="BLT-001",
                           product_gid="gid://shopify/Product/101",
                           variant_gid="gid://shopify/ProductVariant/201",
                           weight={"value": 0.4, "unit": "KILOGRAMS"}),
            ],
        ),
    ])

    fake_returned_order = MagicMock()

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock(return_value=fake_returned_order)) as mock_create:
        result = await sync_shop_orders(db, shop, user)

    assert isinstance(result, ImportResult)
    assert result.imported == 2
    assert result.skipped == 0
    assert result.errors == []
    assert result.products_created == 2
    assert result.variants_created == 2

    # Each create_order received an items list with the FK-linked variant
    assert mock_create.await_count == 2
    for call in mock_create.await_args_list:
        order_create = call.args[1]
        assert len(order_create.items) == 1
        assert order_create.items[0].product_variant_id is not None


@pytest.mark.asyncio
async def test_resync_creates_zero_catalog_rows():
    shop = _make_shop()
    # The two orders already exist in DB.
    db = _make_db(existing_external_ids={"1001", "1002"})
    svc = _make_catalog_service()
    user = MagicMock(); user.id = uuid4()

    payload = _graphql_payload([
        _order_node(
            order_gid="gid://shopify/Order/1001",
            name="#1001",
            line_items=[_line_item(
                title="Wallet", quantity=1, price="49.99", sku="WAL-001",
                product_gid="gid://shopify/Product/100",
                variant_gid="gid://shopify/ProductVariant/200")],
        ),
        _order_node(
            order_gid="gid://shopify/Order/1002",
            name="#1002",
            line_items=[_line_item(
                title="Belt", quantity=2, price="29.00", sku="BLT-001",
                product_gid="gid://shopify/Product/101",
                variant_gid="gid://shopify/ProductVariant/201")],
        ),
    ])

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        result = await sync_shop_orders(db, shop, user)

    assert result.imported == 0
    assert result.skipped == 2
    assert result.products_created == 0
    assert result.variants_created == 0
    mock_create.assert_not_awaited()
    # Helper never reaches catalog service for skipped orders
    svc.find_product_by_external_ref.assert_not_called()


@pytest.mark.asyncio
async def test_empty_sku_falls_back_to_shopify_pattern():
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    user = MagicMock(); user.id = uuid4()

    payload = _graphql_payload([_order_node(
        order_gid="gid://shopify/Order/2000",
        name="#2000",
        line_items=[_line_item(
            title="Custom Item", quantity=1, price="10",
            sku=None,  # ← blank SKU
            product_gid="gid://shopify/Product/500",
            variant_gid="gid://shopify/ProductVariant/600")],
    )])

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        await sync_shop_orders(db, shop, user)

    variant_objs = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ProductVariant)]
    assert len(variant_objs) == 1
    assert variant_objs[0].sku == "shopify-500-600"
    assert variant_objs[0].external_ref == "600"
    # FK propagated into the OrderItemCreate payload
    items = mock_create.await_args.args[1].items
    assert items[0].product_variant_id == variant_objs[0].id


@pytest.mark.asyncio
async def test_blocked_sku_skips_variant_and_no_orphan_product():
    """Q7 lazy-insert: every variant for a fresh product is shop-wide-taken → no Product row."""
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service(taken_skus={"BLOCKED-1"})
    user = MagicMock(); user.id = uuid4()

    payload = _graphql_payload([_order_node(
        order_gid="gid://shopify/Order/3000",
        name="#3000",
        line_items=[_line_item(
            title="Hat", quantity=1, price="20", sku="BLOCKED-1",
            product_gid="gid://shopify/Product/700",
            variant_gid="gid://shopify/ProductVariant/800")],
    )])

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        result = await sync_shop_orders(db, shop, user)

    products_added = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Product)]
    variants_added = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ProductVariant)]
    assert products_added == []
    assert variants_added == []
    assert result.products_created == 0
    assert result.variants_created == 0
    # Order still imported, OrderItem just has no FK
    assert result.imported == 1
    items = mock_create.await_args.args[1].items
    assert items[0].product_variant_id is None


@pytest.mark.asyncio
async def test_in_sync_dedup_same_product_two_orders():
    """Same Shopify product across two orders → one Product insert, both items FK-linked."""
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    user = MagicMock(); user.id = uuid4()

    same_product = "gid://shopify/Product/900"
    same_variant = "gid://shopify/ProductVariant/901"

    payload = _graphql_payload([
        _order_node(
            order_gid="gid://shopify/Order/4001",
            name="#4001",
            line_items=[_line_item(
                title="Bag", quantity=1, price="30", sku="BAG-1",
                product_gid=same_product, variant_gid=same_variant)],
        ),
        _order_node(
            order_gid="gid://shopify/Order/4002",
            name="#4002",
            line_items=[_line_item(
                title="Bag", quantity=2, price="30", sku="BAG-1",
                product_gid=same_product, variant_gid=same_variant)],
        ),
    ])

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        result = await sync_shop_orders(db, shop, user)

    assert result.products_created == 1
    assert result.variants_created == 1
    # Helper hit the catalog service exactly once (cache covered the second order)
    assert svc.find_product_by_external_ref.await_count == 1

    # Both OrderItems FK-link to the same variant
    fk_ids = [call.args[1].items[0].product_variant_id for call in mock_create.await_args_list]
    assert fk_ids[0] == fk_ids[1] is not None


@pytest.mark.asyncio
async def test_snapshot_via_real_create_order_flush_ordering():
    """Verifies the explicit db.flush() before create_order — without it, a strict-mode
    session would not see the just-added ProductVariant inside _apply_variant_snapshot.
    Here we just assert that db.flush was called between the catalog adds and create_order."""
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    user = MagicMock(); user.id = uuid4()

    payload = _graphql_payload([_order_node(
        order_gid="gid://shopify/Order/5000",
        name="#5000",
        line_items=[_line_item(
            title="Belt", quantity=1, price="20", sku="BLT-9",
            product_gid="gid://shopify/Product/950",
            variant_gid="gid://shopify/ProductVariant/951",
            weight={"value": 100, "unit": "GRAMS"})],
    )])

    call_order = []
    db.add = MagicMock(side_effect=lambda obj: call_order.append(("add", type(obj).__name__)))
    db.flush = AsyncMock(side_effect=lambda: call_order.append(("flush", None)))

    async def fake_create(db_arg, payload_arg, user_arg, **kwargs):
        call_order.append(("create_order", payload_arg.external_id))

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock(side_effect=fake_create)):
        await sync_shop_orders(db, shop, user)

    # Adds happen, then a flush, then create_order — that ordering is the IMP-2 contract.
    add_indices = [i for i, e in enumerate(call_order) if e[0] == "add"]
    flush_indices = [i for i, e in enumerate(call_order) if e[0] == "flush"]
    create_indices = [i for i, e in enumerate(call_order) if e[0] == "create_order"]
    assert add_indices, "expected catalog rows to be added"
    assert any(f > max(add_indices) for f in flush_indices), \
        "expected at least one flush AFTER the catalog adds"
    assert create_indices[0] > min(f for f in flush_indices if f > max(add_indices)), \
        "create_order should run after the post-add flush"


@pytest.mark.asyncio
async def test_line_item_with_null_variant_creates_unlinked_order_item():
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    user = MagicMock(); user.id = uuid4()

    null_variant_li = {
        "node": {
            "title": "Custom Engraving",
            "quantity": 1,
            "originalUnitPriceSet": {"shopMoney": {"amount": "5", "currencyCode": "USD"}},
            "variant": None,  # ← deleted variant in Shopify
        }
    }
    payload = _graphql_payload([_order_node(
        order_gid="gid://shopify/Order/6000", name="#6000", line_items=[null_variant_li])])

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        result = await sync_shop_orders(db, shop, user)

    assert result.imported == 1
    assert result.products_created == 0
    assert result.variants_created == 0
    items = mock_create.await_args.args[1].items
    assert len(items) == 1
    assert items[0].product_variant_id is None
    assert items[0].title == "Custom Engraving"
    svc.find_product_by_external_ref.assert_not_called()


@pytest.mark.asyncio
async def test_line_item_with_null_product_creates_unlinked_order_item():
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    user = MagicMock(); user.id = uuid4()

    li = {
        "node": {
            "title": "Mystery",
            "quantity": 1,
            "originalUnitPriceSet": {"shopMoney": {"amount": "7", "currencyCode": "USD"}},
            "variant": {
                "id": "gid://shopify/ProductVariant/abc",
                "sku": "MYST",
                "title": "Default Title",
                "product": None,  # ← orphan variant
                "inventoryItem": None,
            },
        }
    }
    payload = _graphql_payload([_order_node(
        order_gid="gid://shopify/Order/6100", name="#6100", line_items=[li])])

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        result = await sync_shop_orders(db, shop, user)

    assert result.imported == 1
    assert result.products_created == 0
    assert result.variants_created == 0
    items = mock_create.await_args.args[1].items
    assert items[0].product_variant_id is None


@pytest.mark.asyncio
async def test_default_title_variant_stored_as_null_variant_name():
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    user = MagicMock(); user.id = uuid4()

    payload = _graphql_payload([_order_node(
        order_gid="gid://shopify/Order/7000", name="#7000",
        line_items=[_line_item(
            title="Single-Variant Product", quantity=1, price="15", sku="SVP-1",
            product_gid="gid://shopify/Product/1100",
            variant_gid="gid://shopify/ProductVariant/1101",
            variant_title="Default Title")],  # Shopify sentinel
    )])

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock()):
        await sync_shop_orders(db, shop, user)

    variants = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ProductVariant)]
    assert len(variants) == 1
    assert variants[0].variant_name is None


@pytest.mark.asyncio
async def test_real_variant_title_preserved():
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    user = MagicMock(); user.id = uuid4()

    payload = _graphql_payload([_order_node(
        order_gid="gid://shopify/Order/7100", name="#7100",
        line_items=[_line_item(
            title="Multi-Variant", quantity=1, price="25", sku="MV-LRG",
            product_gid="gid://shopify/Product/1200",
            variant_gid="gid://shopify/ProductVariant/1201",
            variant_title="Brown / Large")],
    )])

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock()):
        await sync_shop_orders(db, shop, user)

    variants = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ProductVariant)]
    assert variants[0].variant_name == "Brown / Large"


@pytest.mark.asyncio
async def test_returns_import_result_shape():
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    user = MagicMock(); user.id = uuid4()

    payload = _graphql_payload([])

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc):
        result = await sync_shop_orders(db, shop, user)

    assert isinstance(result, ImportResult)
    dumped = result.model_dump()
    for key in ("imported", "skipped", "errors", "products_created", "variants_created"):
        assert key in dumped


@pytest.mark.asyncio
async def test_per_order_error_isolation_with_bad_payload():
    """A bad order (missing createdAt) raises during processing → captured in errors,
    other orders still imported."""
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    user = MagicMock(); user.id = uuid4()

    bad_order = {
        "node": {
            "id": "gid://shopify/Order/9000",
            "name": "#9000",
            # missing createdAt → datetime.fromisoformat will raise
            "totalPriceSet": {"shopMoney": {"amount": "10", "currencyCode": "USD"}},
            "customer": {"firstName": "X", "lastName": "Y", "email": "x@y.com"},
            "shippingAddress": {},
            "lineItems": {"edges": []},
        }
    }
    good_order = _order_node(
        order_gid="gid://shopify/Order/9001", name="#9001",
        line_items=[_line_item(
            title="Good", quantity=1, price="20", sku="GOOD-1",
            product_gid="gid://shopify/Product/9001",
            variant_gid="gid://shopify/ProductVariant/9001v")],
    )
    payload = _graphql_payload([bad_order, good_order])

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock()):
        result = await sync_shop_orders(db, shop, user)

    assert result.imported == 1
    assert len(result.errors) == 1
    assert result.errors[0]["external_id"] == "9000"
    # Catalog work for the good order still happened
    assert result.products_created == 1
    assert result.variants_created == 1


@pytest.mark.asyncio
async def test_non_shopify_shop_returns_empty_result():
    shop = _make_shop()
    shop.platform = ShopPlatform.ETSY
    db = _make_db()
    user = MagicMock(); user.id = uuid4()

    with patch("services.shopify_sync.decrypt_value", return_value="tok"):
        result = await sync_shop_orders(db, shop, user)

    assert isinstance(result, ImportResult)
    assert result.imported == 0
    assert result.products_created == 0


@pytest.mark.asyncio
async def test_missing_credentials_returns_empty_result():
    shop = _make_shop()
    shop.shopify_access_token_encrypted = None
    db = _make_db()
    user = MagicMock(); user.id = uuid4()

    result = await sync_shop_orders(db, shop, user)

    assert isinstance(result, ImportResult)
    assert result.imported == 0


# ---------- router response shape (back-compat) ----------


def test_router_response_preserves_synced_count_key():
    """The shops router response merges legacy `synced_count` with the new ImportResult fields."""
    result = ImportResult(imported=5, skipped=2, errors=[], products_created=3, variants_created=4)
    response = {
        "status": "success",
        "synced_count": result.imported,
        **result.model_dump(),
    }
    assert response["synced_count"] == 5
    assert response["imported"] == 5
    assert response["skipped"] == 2
    assert response["products_created"] == 3
    assert response["variants_created"] == 4


# ---------- BUG-8: order title resolution ----------


@pytest.mark.asyncio
async def test_order_title_uses_first_line_item_for_single_item_order():
    """BUG-8 regression: title comes from line item, not Shopify order code."""
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    user = MagicMock(); user.id = uuid4()

    payload = _graphql_payload([_order_node(
        order_gid="gid://shopify/Order/91890",
        name="#91890_1580",
        line_items=[_line_item(
            title="Heavy Mushroom Keychain", quantity=1, price="19.00",
            sku="HMK-1",
            product_gid="gid://shopify/Product/1100",
            variant_gid="gid://shopify/ProductVariant/1200")],
    )])

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        await sync_shop_orders(db, shop, user)

    order_create = mock_create.await_args.args[1]
    assert order_create.title == "Heavy Mushroom Keychain"
    assert order_create.title != "#91890_1580"


@pytest.mark.asyncio
async def test_order_title_uses_first_line_item_with_multiple_items():
    """Multi-item order: first line item wins (mirrors Etsy parser behaviour)."""
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    user = MagicMock(); user.id = uuid4()

    payload = _graphql_payload([_order_node(
        order_gid="gid://shopify/Order/91891",
        name="#91890_1581",
        line_items=[
            _line_item(title="Wallet", quantity=1, price="49.99", sku="WAL-X",
                       product_gid="gid://shopify/Product/1101",
                       variant_gid="gid://shopify/ProductVariant/1201"),
            _line_item(title="Belt", quantity=1, price="29.00", sku="BLT-X",
                       product_gid="gid://shopify/Product/1102",
                       variant_gid="gid://shopify/ProductVariant/1202"),
            _line_item(title="Keychain", quantity=1, price="9.00", sku="KCH-X",
                       product_gid="gid://shopify/Product/1103",
                       variant_gid="gid://shopify/ProductVariant/1203"),
        ],
    )])

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        await sync_shop_orders(db, shop, user)

    order_create = mock_create.await_args.args[1]
    assert order_create.title == "Wallet"
    assert len(order_create.items) == 3


@pytest.mark.asyncio
async def test_order_title_falls_back_to_node_name_when_no_line_items():
    """Defensive: zero line items → fall back to Shopify's node.name."""
    shop = _make_shop()
    db = _make_db()
    svc = _make_catalog_service()
    user = MagicMock(); user.id = uuid4()

    payload = _graphql_payload([_order_node(
        order_gid="gid://shopify/Order/91892",
        name="#91890_1582",
        line_items=[],
    )])

    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync._fetch_orders_page", AsyncMock(return_value=payload)), \
         patch("services.shopify_sync.CatalogService", return_value=svc), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        await sync_shop_orders(db, shop, user)

    order_create = mock_create.await_args.args[1]
    assert order_create.title == "#91890_1582"
    assert order_create.items == []
