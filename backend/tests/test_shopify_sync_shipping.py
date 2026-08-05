"""ORDER-SHIPPING-1 — capturing Shopify shipping / discount / tax on the order.

Three things are under test here, and they fail for different reasons:

  1. The MAPPERS. Both Shopify ingest paths read structurally different JSON for
     the same three values, and rule 3 of the spec exists because fixing one and
     forgetting the other is the obvious way to get this wrong. GraphQL and REST
     are covered side by side.
  2. NULL vs 0.00. A missing figure must stay NULL. `_to_decimal` maps absence to
     Decimal("0"), so a mapper wired to it would write "this order shipped free"
     for every payload that never mentioned shipping — the exact defect the
     residual this sprint removes had.
  3. The BALANCE CHECK. The identity was verified against 28 live Lamamarka
     orders; these pin it as arithmetic, including the shipping-discount case
     that does not occur today but would double-subtract if it ever did.

Same mocking style as test_shopify_sync_fees.py: AsyncMock + MagicMock, patch the
fetch seam with canned page bodies, patch create_order and read its kwargs. No
real HTTP, no DB.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from models.shop import ShopPlatform
from services.shopify_sync import (
    ORDERS_QUERY,
    check_order_balance,
    extract_money_breakdown,
    extract_money_breakdown_rest,
    items_gross_from_node,
    sync_shop_orders,
)


# ---------- helpers ----------


def _make_shop():
    shop = MagicMock()
    shop.id = uuid4()
    shop.name = "Lamamarka"
    shop.platform = ShopPlatform.SHOPIFY
    shop.shopify_store_url = "test.myshopify.com"
    shop.shopify_access_token_encrypted = b"encrypted"
    shop.last_synced_at = None
    # SHOP-FEE-1: must be an explicit None, not left to MagicMock's auto-attr —
    # a bare mock reaching compute_platform_fee raises InvalidOperation, which
    # the per-order `except Exception` swallows as a silent import failure.
    shop.fee_percent = None
    return shop


def _make_db():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    async def execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        return result

    db.execute = AsyncMock(side_effect=execute)
    return db


def _line(unit, qty=1, title="Item"):
    return {
        "node": {
            "title": title,
            "quantity": qty,
            "originalUnitPriceSet": {"shopMoney": {"amount": unit, "currencyCode": "USD"}},
            "variant": None,
        }
    }


def _order_node(
    *,
    order_id=7410546344092,
    name="91890_1841",
    amount="49.50",
    subtotal="40.50",
    shipping="9.00",
    discount="4.49",
    tax="0.00",
    lines=None,
    omit_breakdown=False,
):
    """Order 91890_1841 by default — the order the bug report names."""
    node = {
        "id": f"gid://shopify/Order/{order_id}",
        "name": name,
        "createdAt": "2026-07-30T02:44:55Z",
        "closedAt": None,
        "cancelledAt": None,
        "displayFinancialStatus": "PAID",
        "displayFulfillmentStatus": "UNFULFILLED",
        "totalPriceSet": {"shopMoney": {"amount": amount, "currencyCode": "USD"}},
        "note": None,
        "customer": {"firstName": "Nina", "lastName": "R", "email": "n@example.com"},
        "shippingAddress": {"name": "Nina R", "phone": None, "address1": None,
                            "address2": None, "city": None, "provinceCode": None,
                            "zip": None, "countryCodeV2": "US"},
        "lineItems": {"edges": lines if lines is not None else [_line("44.99")]},
    }
    if not omit_breakdown:
        node["subtotalPriceSet"] = {"shopMoney": {"amount": subtotal}}
        node["totalShippingPriceSet"] = {"shopMoney": {"amount": shipping}}
        node["totalDiscountsSet"] = {"shopMoney": {"amount": discount}}
        node["totalTaxSet"] = {"shopMoney": {"amount": tax}}
    return {"node": node}


def _page(edges):
    return {
        "data": {"orders": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "edges": edges,
        }},
        "extensions": {"cost": {"requestedQueryCost": 10, "throttleStatus": {
            "maximumAvailable": 1000.0, "currentlyAvailable": 990, "restoreRate": 50.0}}},
    }


async def _run_sync(shop, node):
    """Sync one order node and return the kwargs create_order was called with."""
    db = _make_db()
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page",
               AsyncMock(return_value=_page([node]))), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        await sync_shop_orders(db, shop, MagicMock())
    assert mock_create.await_count == 1
    return mock_create.await_args.kwargs


# ---------- the GraphQL query asks for the fields at all ----------


def test_orders_query_requests_the_breakdown():
    """The mapper cannot map what the document never asked for. Before this
    sprint ORDERS_QUERY selected `totalPriceSet` and nothing else."""
    for field in (
        "totalShippingPriceSet",
        "totalDiscountsSet",
        "totalTaxSet",
        "subtotalPriceSet",
    ):
        assert field in ORDERS_QUERY, f"{field} missing from ORDERS_QUERY"


def test_orders_query_uses_shop_money_only():
    """Convention in this file: every money field is read from shopMoney. A
    presentment figure would be in the CUSTOMER's currency and would not match
    the order's own `currency` column."""
    assert "presentmentMoney" not in ORDERS_QUERY


# ---------- GraphQL mapper ----------


def test_graphql_mapper_reads_the_three_figures():
    b = extract_money_breakdown(_order_node()["node"])
    assert b["shipping_revenue"] == Decimal("9.00")
    assert b["discount_total"] == Decimal("4.49")
    assert b["tax_total"] == Decimal("0.00")
    assert b["subtotal"] == Decimal("40.50")


def test_graphql_mapper_keeps_the_discount_positive():
    """Shopify reports discounts positive; rule 2 keeps that sign so no consumer
    has to guess the convention. The subtraction happens at render time."""
    b = extract_money_breakdown(_order_node(discount="4.49")["node"])
    assert b["discount_total"] > 0


def test_graphql_mapper_maps_absence_to_none_not_zero():
    """A payload that never mentions shipping means UNKNOWN. Writing 0.00 there
    would claim the order shipped free."""
    b = extract_money_breakdown(_order_node(omit_breakdown=True)["node"])
    assert b["shipping_revenue"] is None
    assert b["discount_total"] is None
    assert b["tax_total"] is None


def test_graphql_mapper_keeps_a_real_zero():
    """0.00 from Shopify IS a fact — free shipping — and must survive as one."""
    b = extract_money_breakdown(_order_node(shipping="0.00")["node"])
    assert b["shipping_revenue"] == Decimal("0")
    assert b["shipping_revenue"] is not None


def test_items_gross_uses_pre_discount_unit_prices():
    """The card's "Items subtotal" row sums OrderItem.unit_price, which the
    mapper fills from originalUnitPriceSet — i.e. PRE-discount. On 91890_1841
    that is 44.99, not Shopify's post-discount subtotal of 40.50."""
    node = _order_node()["node"]
    assert items_gross_from_node(node) == Decimal("44.99")
    assert items_gross_from_node(node) != Decimal("40.50")


def test_items_gross_multiplies_by_quantity():
    node = _order_node(lines=[_line("39.99", qty=5)])["node"]
    assert items_gross_from_node(node) == Decimal("199.95")


# ---------- REST / webhook mapper (rule 3: both paths, or neither) ----------


def test_rest_mapper_reads_the_same_figures_from_snake_case():
    b = extract_money_breakdown_rest({
        "total_shipping_price_set": {"shop_money": {"amount": "9.00"}},
        "total_discounts": "4.49",
        "total_tax": "0.00",
        "subtotal_price": "40.50",
    })
    assert b["shipping_revenue"] == Decimal("9.00")
    assert b["discount_total"] == Decimal("4.49")
    assert b["tax_total"] == Decimal("0.00")
    assert b["subtotal"] == Decimal("40.50")


def test_rest_mapper_falls_back_to_shipping_lines():
    """Only shipping arrives as a money-set in REST. If that key is absent the
    shipping lines carry the same number."""
    b = extract_money_breakdown_rest({
        "shipping_lines": [
            {"discounted_price": "5.00"},
            {"discounted_price": "4.00"},
        ],
        "total_discounts": "0.00",
        "total_tax": "0.00",
    })
    assert b["shipping_revenue"] == Decimal("9.00")


def test_rest_mapper_maps_absence_to_none_not_zero():
    b = extract_money_breakdown_rest({"id": 1})
    assert b["shipping_revenue"] is None
    assert b["discount_total"] is None
    assert b["tax_total"] is None


def test_both_mappers_agree_on_the_same_order():
    """The whole point of rule 3. 91890_1841 through either path must produce
    identical figures — an order landing on the webhook instead of the poll is
    priced the same."""
    gql = extract_money_breakdown(_order_node()["node"])
    rest = extract_money_breakdown_rest({
        "total_shipping_price_set": {"shop_money": {"amount": "9.00"}},
        "total_discounts": "4.49",
        "total_tax": "0.00",
        "subtotal_price": "40.50",
    })
    for key in ("shipping_revenue", "discount_total", "tax_total", "subtotal"):
        assert gql[key] == rest[key], key


# ---------- balance check ----------


def test_balance_holds_on_the_reported_order():
    """91890_1841, live figures: 44.99 items − 4.49 discount + 9.00 shipping
    + 0 tax = 49.50, and Shopify's own 40.50 + 9.00 + 0 = 49.50."""
    assert check_order_balance(
        total=Decimal("49.50"),
        shipping=Decimal("9.00"),
        discount=Decimal("4.49"),
        tax=Decimal("0.00"),
        subtotal=Decimal("40.50"),
        items_gross=Decimal("44.99"),
    ) is None


def test_balance_holds_with_tax():
    """91890_1820: 134.97 items − 44.99 + 9.00 shipping + 6.93 tax = 105.91."""
    assert check_order_balance(
        total=Decimal("105.91"),
        shipping=Decimal("9.00"),
        discount=Decimal("44.99"),
        tax=Decimal("6.93"),
        subtotal=Decimal("89.98"),
        items_gross=Decimal("134.97"),
    ) is None


def test_balance_flags_shopify_internal_inconsistency():
    assert check_order_balance(
        total=Decimal("49.50"),
        shipping=Decimal("9.00"),
        discount=Decimal("4.49"),
        tax=Decimal("0.00"),
        subtotal=Decimal("35.00"),   # 35 + 9 + 0 != 49.50
        items_gross=Decimal("44.99"),
    ) == "shopify"


def test_balance_flags_a_short_item_snapshot():
    """`lineItems(first: 50)` truncates a >50-line order, so the money is fine
    but the card's rows would not add up. Reported as "items", separately from
    "shopify", because only one of the two means the figures are suspect."""
    assert check_order_balance(
        total=Decimal("49.50"),
        shipping=Decimal("9.00"),
        discount=Decimal("4.49"),
        tax=Decimal("0.00"),
        subtotal=Decimal("40.50"),
        items_gross=Decimal("20.00"),  # half the lines missing
    ) == "items"


def test_balance_catches_a_double_subtracted_shipping_discount():
    """The one future scenario that breaks the identity. Shopify's
    ShippingLine.discountedPriceSet only folds in cart-level free-shipping
    discounts from API 2024-07, and this client pins 2024-04 — so a free-shipping
    promo could report shipping ALREADY net of a discount that totalDiscountsSet
    also counts. No such order exists in the data today (every discount on record
    targets LINE_ITEM), but if one lands, it must not pass silently.

    Here: 44.99 items, a 9.00 shipping charge fully discounted to 0.00, so the
    customer paid 44.99 — but totalDiscounts reports 9.00 as well.
    """
    assert check_order_balance(
        total=Decimal("44.99"),
        shipping=Decimal("0.00"),
        discount=Decimal("9.00"),
        tax=Decimal("0.00"),
        subtotal=Decimal("44.99"),
        items_gross=Decimal("44.99"),
    ) == "items"


def test_balance_ignores_an_order_with_no_items():
    """The webhook path creates no OrderItem rows at all, so a 0 items_gross is
    absence, not a mismatch."""
    assert check_order_balance(
        total=Decimal("49.50"),
        shipping=Decimal("9.00"),
        discount=Decimal("4.49"),
        tax=Decimal("0.00"),
        subtotal=Decimal("40.50"),
        items_gross=Decimal("0"),
    ) is None


def test_balance_ignores_an_order_with_nothing_captured():
    """Nothing was captured, so there is no decomposition to disagree with the
    total. Absence is reported by the columns staying NULL."""
    assert check_order_balance(
        total=Decimal("49.50"),
        shipping=None, discount=None, tax=None,
        subtotal=None,
        items_gross=Decimal("44.99"),
    ) is None


def test_balance_tolerates_sub_cent_noise():
    assert check_order_balance(
        total=Decimal("49.50"),
        shipping=Decimal("9.00"),
        discount=Decimal("4.49"),
        tax=Decimal("0.00"),
        subtotal=Decimal("40.499"),
        items_gross=Decimal("44.99"),
    ) is None


# ---------- the sync write site ----------


@pytest.mark.asyncio
async def test_sync_passes_the_breakdown_to_create_order():
    kwargs = await _run_sync(_make_shop(), _order_node())
    assert kwargs["shipping_revenue"] == Decimal("9.00")
    assert kwargs["discount_total"] == Decimal("4.49")
    assert kwargs["tax_total"] == Decimal("0.00")


@pytest.mark.asyncio
async def test_sync_passes_none_when_the_payload_omits_them():
    kwargs = await _run_sync(_make_shop(), _order_node(omit_breakdown=True))
    assert kwargs["shipping_revenue"] is None
    assert kwargs["discount_total"] is None
    assert kwargs["tax_total"] is None


@pytest.mark.asyncio
async def test_sync_imports_an_unbalanced_order_anyway():
    """Store anyway and flag (settled 2026-08-05). An imbalance is information
    about an order, not grounds for refusing to import it — refusing would lose
    real revenue over what is usually just a truncated line-item snapshot."""
    db = _make_db()
    node = _order_node(subtotal="35.00")  # 35 + 9 + 0 != 49.50
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page",
               AsyncMock(return_value=_page([node]))), \
         patch("services.shopify_sync.create_order", AsyncMock()) as mock_create:
        result = await sync_shop_orders(db, _make_shop(), MagicMock())

    assert result.imported == 1
    assert result.errors == []
    assert result.unbalanced == 1
    # ...and the figures still landed.
    assert mock_create.await_args.kwargs["shipping_revenue"] == Decimal("9.00")


@pytest.mark.asyncio
async def test_sync_reports_zero_unbalanced_on_a_clean_order():
    db = _make_db()
    with patch("services.shopify_sync.decrypt_value", return_value="tok"), \
         patch("services.shopify_sync.CatalogService", return_value=MagicMock()), \
         patch("services.shopify_sync._fetch_orders_page",
               AsyncMock(return_value=_page([_order_node()]))), \
         patch("services.shopify_sync.create_order", AsyncMock()):
        result = await sync_shop_orders(db, _make_shop(), MagicMock())
    assert result.unbalanced == 0


@pytest.mark.asyncio
async def test_real_create_order_lands_the_breakdown_on_the_order_row():
    """The sync tests above mock create_order, so on their own they would still
    pass if the kwargs were computed and then dropped on the floor. This one
    drives the real create_order and reads the Order object it built.
    """
    from models.user import UserRole
    from schemas.order import OrderCreate
    from services.order_service import create_order

    captured = {}

    db = MagicMock()
    db.add = MagicMock(side_effect=lambda obj: captured.setdefault(
        type(obj).__name__, obj
    ))
    db.flush = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(
        scalar_one_or_none=MagicMock(return_value=MagicMock(id=uuid4()))
    ))

    user = MagicMock()
    user.id = uuid4()
    user.role = UserRole.OWNER

    payload = OrderCreate(
        shop_id=uuid4(), email="n@example.com", full_name="Nina R",
        external_id="7410546344092", title="Money Clip",
        total_price=49.50, currency="USD",
        ordered_at="2026-07-30T02:44:55Z",
    )

    with patch("services.order_service.upsert_customer",
               AsyncMock(return_value=MagicMock(id=uuid4()))), \
         patch("services.order_service.get_order_detail", AsyncMock()):
        await create_order(
            db, payload, user,
            shipping_revenue=Decimal("9.00"),
            discount_total=Decimal("4.49"),
            tax_total=Decimal("0.00"),
        )

    order = captured["Order"]
    assert order.shipping_revenue == Decimal("9.00")
    assert order.discount_total == Decimal("4.49")
    assert order.tax_total == Decimal("0.00")


@pytest.mark.asyncio
async def test_create_order_leaves_them_null_for_manual_entry():
    """Manual entry passes nothing, and NULL is the honest answer: no channel
    ever reported a shipping figure for that order."""
    from models.user import UserRole
    from schemas.order import OrderCreate
    from services.order_service import create_order

    captured = {}
    db = MagicMock()
    db.add = MagicMock(side_effect=lambda obj: captured.setdefault(
        type(obj).__name__, obj
    ))
    db.flush = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(
        scalar_one_or_none=MagicMock(return_value=MagicMock(id=uuid4()))
    ))

    user = MagicMock()
    user.id = uuid4()
    user.role = UserRole.OWNER

    payload = OrderCreate(
        shop_id=uuid4(), email="a@b.c", full_name="A B",
        external_id="MANUAL-1", title="Manual", total_price=100.0,
        currency="UAH", ordered_at="2026-08-05T10:00:00Z",
    )

    with patch("services.order_service.upsert_customer",
               AsyncMock(return_value=MagicMock(id=uuid4()))), \
         patch("services.order_service.get_order_detail", AsyncMock()):
        await create_order(db, payload, user)

    order = captured["Order"]
    assert order.shipping_revenue is None
    assert order.discount_total is None
    assert order.tax_total is None


def test_the_three_fields_are_not_writable_from_the_public_body():
    """They are facts reported by a channel. `OrderCreate` is the public POST
    body and `OrderUpdate` the public PATCH body — a manual writer must not be
    able to mint a shipping figure indistinguishable from a captured one."""
    from schemas.order import OrderCreate, OrderUpdate

    for schema in (OrderCreate, OrderUpdate):
        for field in ("shipping_revenue", "discount_total", "tax_total"):
            assert field not in schema.model_fields, f"{field} on {schema.__name__}"
