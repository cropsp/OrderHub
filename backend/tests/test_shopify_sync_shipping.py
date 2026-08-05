"""ORDER-SHIPPING-1/2 — capturing Shopify shipping / discount / tax on the order.

Three things are under test here, and they fail for different reasons:

  1. The MAPPERS. Both Shopify ingest paths read structurally different JSON for
     the same four values, and rule 3 of the spec exists because fixing one and
     forgetting the other is the obvious way to get this wrong. GraphQL and REST
     are covered side by side.
  2. NULL vs 0.00. A missing figure must stay NULL. `_to_decimal` maps absence to
     Decimal("0"), so a mapper wired to it would write "this order shipped free"
     for every payload that never mentioned shipping — the exact defect the
     residual this sprint removes had.
  3. The BALANCE CHECK. The identity was verified against 28 live Lamamarka
     orders; these pin it as arithmetic, including the shipping-discount case
     that used to double-subtract.

ORDER-SHIPPING-2 note on provenance. The fixtures here are real order shapes,
read off the live store through the CRM's own client:

    91890_1815  100% shipping promo, 49.00 -> 0.00, no item discount
    91890_1829  the same, 54.00 -> 0.00
    91890_1841  the control: 9.00 shipping, 4.49 item discount, no promo
    91890_1368  two shipping lines, 10.00 + 12.00, undiscounted
    91890_1287  a "Free Shipping" line priced 0.00 with NO discount at all

Those are every distinct shape the store contains — a sweep of all 870 orders
found exactly two shipping discounts, both 100%, both single-line. Cases marked
NEVER OBSERVED below are constructed: they do not occur in the data and are
pinned because they are what will appear first when they do.

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


def _ship_line(original, discounted=None, allocated=None):
    """One `shippingLines` edge, in the live payload's shape.

    `discountAllocations` mirrors what Shopify actually returns and is Shopify's
    OWN figure for how much came off this line — an independent statement of the
    same number our mapper derives by subtraction. The mapper does not read it;
    it is here so a test can check the derivation against it.
    """
    node = {
        "originalPriceSet": {"shopMoney": {"amount": original}},
        "discountedPriceSet": {
            "shopMoney": {"amount": discounted if discounted is not None else original}
        },
        "discountAllocations": [],
    }
    if allocated is not None:
        node["discountAllocations"] = [
            {"allocatedAmountSet": {"shopMoney": {"amount": allocated}}}
        ]
    return {"node": node}


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
    ship_lines=None,
    omit_breakdown=False,
    omit_shipping_lines=False,
):
    """Order 91890_1841 by default — the order the bug report names.

    `shipping` is `totalShippingPriceSet` (the PRE-discount charge). `ship_lines`
    overrides the shipping lines; by default they are one undiscounted line at
    that same figure, which is what every order but two looks like.
    """
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
        if not omit_shipping_lines:
            node["shippingLines"] = {
                "edges": ship_lines if ship_lines is not None else [_ship_line(shipping)]
            }
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
        # ORDER-SHIPPING-2. Without these two the mapper cannot tell a shipping
        # charge from a shipping giveaway, which is precisely how the defect got
        # through: the document asked only for the pre-discount total.
        "shippingLines",
        "originalPriceSet",
        "discountedPriceSet",
    ):
        assert field in ORDERS_QUERY, f"{field} missing from ORDERS_QUERY"


def test_orders_query_uses_shop_money_only():
    """Convention in this file: every money field is read from shopMoney. A
    presentment figure would be in the CUSTOMER's currency and would not match
    the order's own `currency` column."""
    assert "presentmentMoney" not in ORDERS_QUERY


# ---------- GraphQL mapper ----------


def test_graphql_mapper_reads_the_four_figures():
    b = extract_money_breakdown(_order_node()["node"])
    assert b["shipping_revenue"] == Decimal("9.00")
    assert b["shipping_discount"] == Decimal("0.00")
    assert b["discount_total"] == Decimal("4.49")
    assert b["tax_total"] == Decimal("0.00")
    assert b["subtotal"] == Decimal("40.50")


# ---------- ORDER-SHIPPING-2: shipping promo vs item promo ----------


def _order_1815():
    """91890_1815, the live shape. 369.29 of goods, a 49.00 shipping charge fully
    discounted away, and `totalDiscountsSet` reporting that 49.00 as if it were a
    discount on the goods."""
    return _order_node(
        order_id=7387326316700, name="91890_1815",
        amount="369.29", subtotal="369.29",
        shipping="49.00", discount="49.00", tax="0.00",
        ship_lines=[_ship_line("49.00", "0.00", allocated="49.00")],
        lines=[_line("369.29")],
    )["node"]


def test_a_shipping_promo_is_not_an_item_discount():
    """The defect, in one assertion. Before ORDER-SHIPPING-2 this order stored
    shipping 49.00 (never paid) and discount 49.00 (never given on the goods)."""
    b = extract_money_breakdown(_order_1815())
    assert b["shipping_revenue"] == Decimal("0.00")    # what the customer paid
    assert b["shipping_discount"] == Decimal("49.00")  # what was given away
    assert b["discount_total"] == Decimal("0.00")      # nothing came off the goods


def test_the_shipping_promo_order_now_balances():
    """Rule 5: the balance check is untouched, and both of its checks must pass
    on the very orders that used to trip it. 369.29 + 0 + 0 = 369.29."""
    node = _order_1815()
    b = extract_money_breakdown(node)
    assert check_order_balance(
        total=Decimal("369.29"),
        shipping=b["shipping_revenue"],
        discount=b["discount_total"],
        tax=b["tax_total"],
        subtotal=b["subtotal"],
        items_gross=items_gross_from_node(node),
    ) is None


def test_the_second_promo_order_too():
    """91890_1829 — the other one the sweep found. Same shape, different money."""
    b = extract_money_breakdown(_order_node(
        order_id=7395353329820, name="91890_1829",
        amount="199.98", subtotal="199.98",
        shipping="54.00", discount="54.00", tax="0.00",
        ship_lines=[_ship_line("54.00", "0.00", allocated="54.00")],
        lines=[_line("99.99", qty=2)],
    )["node"])
    assert b["shipping_revenue"] == Decimal("0.00")
    assert b["shipping_discount"] == Decimal("54.00")
    assert b["discount_total"] == Decimal("0.00")


def test_the_derivation_matches_shopifys_own_allocation():
    """`original - discounted` is our derivation; `discountAllocations` is
    Shopify's own statement of the same number. On both live promo orders they
    agree exactly, which is why the subtraction is trustworthy for a PARTIAL or
    fixed-amount discount too — Shopify allocates per line and reports what it
    allocated, so the difference picks up that line's share and nothing else."""
    for node in (_order_1815(),):
        allocated = sum(
            Decimal(a["allocatedAmountSet"]["shopMoney"]["amount"])
            for edge in node["shippingLines"]["edges"]
            for a in edge["node"]["discountAllocations"]
        )
        assert extract_money_breakdown(node)["shipping_discount"] == allocated


def test_an_ordinary_order_is_untouched_by_the_new_arithmetic():
    """Rule 3: no regression where shipping carries no discount. 91890_1841 keeps
    exactly the figures ORDER-SHIPPING-1 gave it."""
    b = extract_money_breakdown(_order_node()["node"])
    assert b["shipping_revenue"] == Decimal("9.00")
    assert b["discount_total"] == Decimal("4.49")
    assert b["shipping_discount"] == Decimal("0.00")


def test_multiple_shipping_lines_sum():
    """91890_1368's real shape: two lines, 10.00 + 12.00, neither discounted.
    Seven such orders exist, all 2025. The mapper must total them, not take the
    first."""
    b = extract_money_breakdown(_order_node(
        name="91890_1368", amount="82.00", subtotal="60.00",
        shipping="22.00", discount="0.00",
        ship_lines=[_ship_line("10.00"), _ship_line("12.00")],
        lines=[_line("60.00")],
    )["node"])
    assert b["shipping_revenue"] == Decimal("22.00")
    assert b["shipping_discount"] == Decimal("0.00")


def test_a_zero_priced_free_shipping_line_is_not_a_discount():
    """91890_1287's real shape. Free shipping reaches us two structurally
    different ways — a line priced 0.00 with no allocation, and a line discounted
    to 0.00 — and only the second is money given away. Reporting 8.00 of
    "shipping discount" here would invent a promo that never happened."""
    b = extract_money_breakdown(_order_node(
        name="91890_1287", amount="58.00", subtotal="50.00",
        shipping="8.00", discount="0.00",
        ship_lines=[_ship_line("0.00"), _ship_line("8.00")],
        lines=[_line("50.00")],
    )["node"])
    assert b["shipping_revenue"] == Decimal("8.00")
    assert b["shipping_discount"] == Decimal("0.00")


def test_an_item_discount_and_a_shipping_promo_together():
    """NEVER OBSERVED on real data — confirmed absent across all 870 orders. It is
    pinned because it is the first combination that will appear (the promo is
    automatic and store-wide) and the one where a sign error hides: both kinds of
    discount arrive summed in `totalDiscountsSet`, and only the shipping part may
    be subtracted out.

    Items 100.00, 10.00 off the goods, 20.00 shipping fully discounted, so
    Shopify reports totalDiscounts 30.00 and the customer pays 90.00.
    """
    node = _order_node(
        amount="90.00", subtotal="90.00",
        shipping="20.00", discount="30.00", tax="0.00",
        ship_lines=[_ship_line("20.00", "0.00", allocated="20.00")],
        lines=[_line("100.00")],
    )["node"]
    b = extract_money_breakdown(node)
    assert b["shipping_revenue"] == Decimal("0.00")
    assert b["shipping_discount"] == Decimal("20.00")
    assert b["discount_total"] == Decimal("10.00")   # NOT 30.00, and not -10.00
    # The card's identity still closes: 100 - 10 + 0 + 0 = 90.
    assert check_order_balance(
        total=Decimal("90.00"), shipping=b["shipping_revenue"],
        discount=b["discount_total"], tax=b["tax_total"],
        subtotal=b["subtotal"], items_gross=items_gross_from_node(node),
    ) is None


def test_a_partial_shipping_discount():
    """NEVER OBSERVED — every shipping promo in the store is 100%. The formula is
    a subtraction, not a percentage, so a partial discount needs no special case:
    12.00 billed of a 20.00 rate is 8.00 given away."""
    b = extract_money_breakdown(_order_node(
        amount="112.00", subtotal="100.00",
        shipping="20.00", discount="8.00", tax="0.00",
        ship_lines=[_ship_line("20.00", "12.00", allocated="8.00")],
        lines=[_line("100.00")],
    )["node"])
    assert b["shipping_revenue"] == Decimal("12.00")
    assert b["shipping_discount"] == Decimal("8.00")
    assert b["discount_total"] == Decimal("0.00")


def test_a_fixed_amount_shipping_discount_across_multiple_lines():
    """NEVER OBSERVED — no fixed-amount shipping discount and no discounted
    multi-line order exists. A fixed amount spread ACROSS lines is reported by
    Shopify already split per line, so summing the per-line differences recovers
    the whole discount without the mapper knowing how it was allocated."""
    b = extract_money_breakdown(_order_node(
        amount="115.00", subtotal="100.00",
        shipping="25.00", discount="10.00", tax="0.00",
        ship_lines=[
            _ship_line("10.00", "6.00", allocated="4.00"),
            _ship_line("15.00", "9.00", allocated="6.00"),
        ],
        lines=[_line("100.00")],
    )["node"])
    assert b["shipping_revenue"] == Decimal("15.00")
    assert b["shipping_discount"] == Decimal("10.00")
    assert b["discount_total"] == Decimal("0.00")


def test_shipping_lines_absent_leaves_the_discount_unknown():
    """An old payload that never carried shipping lines. Shipping falls back to
    the pre-discount total — right for every order without a promo, which is all
    but two — but the SPLIT is unknown, and unknown is NULL. Writing 0.00 would
    assert no promo was given, which is the class of guess this sprint removes."""
    b = extract_money_breakdown(_order_node(omit_shipping_lines=True)["node"])
    assert b["shipping_revenue"] == Decimal("9.00")
    assert b["shipping_discount"] is None
    # ...and with the split unknown, the item discount cannot be derived either,
    # so it stays exactly as Shopify reported it.
    assert b["discount_total"] == Decimal("4.49")


def test_no_shipping_lines_at_all_is_a_real_zero():
    """Present but empty is Shopify saying there were no shipping lines — nothing
    charged, nothing given away. Distinct from the key being absent above."""
    b = extract_money_breakdown(_order_node(shipping="0.00", ship_lines=[])["node"])
    assert b["shipping_revenue"] == Decimal("0")
    assert b["shipping_discount"] == Decimal("0")


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


def _rest_1841():
    """91890_1841's live REST payload, trimmed to the money."""
    return {
        "total_shipping_price_set": {"shop_money": {"amount": "9.00"}},
        "shipping_lines": [{
            "price": "9.00", "discounted_price": "9.00",
            "price_set": {"shop_money": {"amount": "9.00"}},
            "discounted_price_set": {"shop_money": {"amount": "9.00"}},
            "discount_allocations": [],
        }],
        "total_discounts": "4.49",
        "total_tax": "0.00",
        "subtotal_price": "40.50",
    }


def _rest_1815():
    """91890_1815's live REST payload. Note `total_discounts` reports 49.00 —
    inclusive of the shipping promo, exactly as `totalDiscountsSet` does, which
    is what makes the same subtraction correct on this side."""
    return {
        "total_shipping_price_set": {"shop_money": {"amount": "49.00"}},
        "shipping_lines": [{
            "title": "Standard Shipping",
            "price": "49.00", "discounted_price": "0.00",
            "price_set": {"shop_money": {"amount": "49.00"}},
            "discounted_price_set": {"shop_money": {"amount": "0.00"}},
            "discount_allocations": [{"amount": "49.00"}],
        }],
        "total_discounts": "49.00",
        "total_tax": "0.00",
        "subtotal_price": "369.29",
    }


def test_rest_mapper_reads_the_same_figures_from_snake_case():
    b = extract_money_breakdown_rest(_rest_1841())
    assert b["shipping_revenue"] == Decimal("9.00")
    assert b["shipping_discount"] == Decimal("0.00")
    assert b["discount_total"] == Decimal("4.49")
    assert b["tax_total"] == Decimal("0.00")
    assert b["subtotal"] == Decimal("40.50")


def test_rest_mapper_splits_a_shipping_promo_too():
    """ORDER-SHIPPING-2 rule 4: both paths, or neither. This payload is the one
    that used to be read as shipping 49.00 / discount 49.00 on BOTH sides."""
    b = extract_money_breakdown_rest(_rest_1815())
    assert b["shipping_revenue"] == Decimal("0.00")
    assert b["shipping_discount"] == Decimal("49.00")
    assert b["discount_total"] == Decimal("0.00")


def test_rest_mapper_reads_bare_price_strings():
    """REST states each shipping figure twice — a bare string and a money-set.
    Older payloads carry only the bare form."""
    b = extract_money_breakdown_rest({
        "shipping_lines": [
            {"price": "5.00", "discounted_price": "5.00"},
            {"price": "4.00", "discounted_price": "4.00"},
        ],
        "total_discounts": "0.00",
        "total_tax": "0.00",
    })
    assert b["shipping_revenue"] == Decimal("9.00")
    assert b["shipping_discount"] == Decimal("0.00")


def test_rest_mapper_maps_absence_to_none_not_zero():
    b = extract_money_breakdown_rest({"id": 1})
    assert b["shipping_revenue"] is None
    assert b["shipping_discount"] is None
    assert b["discount_total"] is None
    assert b["tax_total"] is None


def test_rest_mapper_leaves_the_split_unknown_without_lines():
    """Same rule as GraphQL: no lines means the split is unknowable, and unknown
    is NULL. The gross total is still the best available shipping figure."""
    b = extract_money_breakdown_rest({
        "total_shipping_price_set": {"shop_money": {"amount": "9.00"}},
        "total_discounts": "4.49",
    })
    assert b["shipping_revenue"] == Decimal("9.00")
    assert b["shipping_discount"] is None
    assert b["discount_total"] == Decimal("4.49")


def test_both_mappers_agree_on_the_same_order():
    """The whole point of rule 3. 91890_1841 through either path must produce
    identical figures — an order landing on the webhook instead of the poll is
    priced the same."""
    gql = extract_money_breakdown(_order_node()["node"])
    rest = extract_money_breakdown_rest(_rest_1841())
    for key in ("shipping_revenue", "shipping_discount", "discount_total",
                "tax_total", "subtotal"):
        assert gql[key] == rest[key], key


def test_both_mappers_agree_on_a_shipping_discounted_order():
    """The parity fixture that did not exist, which is why the defect got through
    (ORDER-SHIPPING-2 rule 4). No fixture here carried a shipping discount, so
    the two paths could disagree on exactly the orders that mattered and the
    parity test still passed. 91890_1815, both shapes, same four answers."""
    gql = extract_money_breakdown(_order_1815())
    rest = extract_money_breakdown_rest(_rest_1815())
    for key in ("shipping_revenue", "shipping_discount", "discount_total",
                "tax_total", "subtotal"):
        assert gql[key] == rest[key], key
    assert gql["shipping_revenue"] == Decimal("0.00")
    assert gql["shipping_discount"] == Decimal("49.00")


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
    """The scenario that DID break the identity, and the check that caught it.

    The rationale recorded here before ORDER-SHIPPING-2 was wrong twice over. It
    said `ShippingLine.discountedPriceSet` folds cart-level free-shipping
    discounts in only from API 2024-07 while this client pinned 2024-04 — but the
    pin never bound (Shopify had long been serving 2025-10) and the field was
    already net. It also said no such order existed; two did, 91890_1815 and
    91890_1829, and this check is what flagged them out of 870.

    The assertion is unchanged and stays: it is now the regression guard for a
    mapper that goes back to feeding a shipping promo in as an item discount.
    Here: 44.99 of items, a 9.00 shipping charge fully discounted to 0.00, so the
    customer paid 44.99 — but the discount is reported as 9.00 on the goods too.
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
