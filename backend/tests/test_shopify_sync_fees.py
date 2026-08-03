"""SHOP-FEE-1 — per-shop fee_percent → order.platform_fee on Shopify sync.

Covers the compute helper in isolation, then the sync write site: which orders
get a fee, what the arithmetic is, and that the provenance token stamped into the
import comment is the exact shape order_service's redaction regex recognises.

Same mocking style as test_shopify_backfill.py: AsyncMock + MagicMock, patch the
fetch seam with canned GraphQL page bodies, patch create_order and read the
kwargs it was called with. No real HTTP, no DB.
"""

from decimal import Decimal, InvalidOperation
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from models.shop import ShopPlatform
from services.order_service import compute_platform_fee, redact_financial_comment
from services.shopify_sync import sync_shop_orders


# ---------- helpers ----------


def _make_shop(fee_percent=None):
    shop = MagicMock()
    shop.id = uuid4()
    shop.name = "MyShop"
    shop.platform = ShopPlatform.SHOPIFY
    shop.shopify_store_url = "test.myshopify.com"
    shop.shopify_access_token_encrypted = b"encrypted"
    shop.last_synced_at = None
    shop.fee_percent = fee_percent
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


def _order_node(*, order_id=1, amount="100.00", cancelled_at=None,
                fulfillment_status="UNFULFILLED"):
    return {
        "node": {
            "id": f"gid://shopify/Order/{order_id}",
            "name": f"#{order_id}",
            "createdAt": "2026-03-15T10:00:00Z",
            "closedAt": None,
            "cancelledAt": cancelled_at,
            "displayFinancialStatus": "PAID",
            "displayFulfillmentStatus": fulfillment_status,
            "totalPriceSet": {"shopMoney": {"amount": amount, "currencyCode": "USD"}},
            "note": None,
            "customer": {"firstName": "T", "lastName": "B", "email": "b@example.com"},
            "shippingAddress": {"name": "T B", "phone": None, "address1": None,
                                "address2": None, "city": None, "provinceCode": None,
                                "zip": None, "countryCodeV2": "US"},
            "lineItems": {"edges": []},
        }
    }


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


# ---------- compute_platform_fee (unit) ----------


def test_compute_returns_none_when_rate_not_configured():
    """NULL rate is 'not priced', which must stay distinguishable from a 0 fee —
    a NULL platform_fee is what keeps the order eligible for a later backfill."""
    assert compute_platform_fee(Decimal("100.00"), None) is None


def test_compute_zero_rate_returns_zero_not_none():
    """A rate of 0 means 'priced, at zero' — a real answer, not 'unconfigured'."""
    assert compute_platform_fee(Decimal("100.00"), Decimal("0")) == Decimal("0.00")


def test_compute_rounds_half_up_to_two_places():
    # 10.05 * 6.5% = 0.65325 → 0.65
    assert compute_platform_fee(Decimal("10.05"), Decimal("6.50")) == Decimal("0.65")
    # 1.00 * 12.5% = 0.125 → 0.13 (HALF_UP, not banker's rounding to 0.12)
    assert compute_platform_fee(Decimal("1.00"), Decimal("12.5")) == Decimal("0.13")


def test_compute_accepts_decimal_float_and_str_identically():
    expected = Decimal("8.00")
    assert compute_platform_fee(Decimal("100.00"), Decimal("8")) == expected
    assert compute_platform_fee(100.0, 8.0) == expected
    assert compute_platform_fee("100.00", "8") == expected


def test_compute_returns_decimal_not_float():
    fee = compute_platform_fee(100.0, 8.0)
    assert isinstance(fee, Decimal)


def test_compute_raises_on_non_numeric_rather_than_yielding_zero():
    """A silent 0 would look like a legitimately-priced order. This is the guard
    that makes the MagicMock-shop hazard in the sync tests fail loudly."""
    with pytest.raises(InvalidOperation):
        compute_platform_fee(MagicMock(), Decimal("8.00"))
    with pytest.raises(InvalidOperation):
        compute_platform_fee(Decimal("100.00"), "not-a-number")


# ---------- sync write site ----------


@pytest.mark.asyncio
async def test_fee_applied_from_shop_percent():
    kwargs = await _run_sync(_make_shop(Decimal("6.50")), _order_node(amount="100.00"))
    assert kwargs["platform_fee"] == Decimal("6.50")


@pytest.mark.asyncio
async def test_no_fee_when_shop_percent_is_null():
    """Today's behaviour for every shop: no rate → no auto fee, platform_fee
    stays NULL. Also the regression guard for a shop fixture that forgets to set
    fee_percent explicitly."""
    kwargs = await _run_sync(_make_shop(None), _order_node(amount="100.00"))
    assert kwargs["platform_fee"] is None


@pytest.mark.asyncio
async def test_fee_rounds_half_up_on_sync():
    kwargs = await _run_sync(_make_shop(Decimal("6.50")), _order_node(amount="10.05"))
    assert kwargs["platform_fee"] == Decimal("0.65")
    assert isinstance(kwargs["platform_fee"], Decimal)


@pytest.mark.asyncio
async def test_fee_computed_from_decimal_not_float():
    """The sync passes total_price to OrderCreate as a float, but the fee is
    computed from the Decimal amount — so no binary-float artefact reaches the
    money column. 0.07 * 33.33% = 0.0233... → 0.02."""
    kwargs = await _run_sync(_make_shop(Decimal("33.33")), _order_node(amount="0.07"))
    assert kwargs["platform_fee"] == Decimal("0.02")


@pytest.mark.asyncio
async def test_zero_total_order_gets_zero_fee():
    kwargs = await _run_sync(_make_shop(Decimal("8.00")), _order_node(amount="0.00"))
    assert kwargs["platform_fee"] == Decimal("0.00")


@pytest.mark.asyncio
async def test_cancelled_order_gets_no_fee():
    """CANCELLED is outside REVENUE_STATUSES, so a fee there is inert in the P&L
    but wrong on the order card — and it would make the backfill's dry-run total
    fail to reconcile against the finance page."""
    node = _order_node(amount="100.00", cancelled_at="2026-03-16T10:00:00Z")
    kwargs = await _run_sync(_make_shop(Decimal("8.00")), node)
    assert kwargs["platform_fee"] is None
    # The rest of the import is unaffected.
    assert kwargs["status"].value == "cancelled"


# ---------- provenance ----------


@pytest.mark.asyncio
async def test_fee_provenance_recorded_in_history_comment():
    kwargs = await _run_sync(_make_shop(Decimal("6.50")), _order_node(amount="100.00"))
    assert "platform_fee: 6.50 @ 6.50%" in kwargs["history_comment"]
    # The original import provenance survives alongside it.
    assert "Imported from Shopify" in kwargs["history_comment"]


@pytest.mark.asyncio
async def test_no_provenance_addendum_when_no_fee():
    kwargs = await _run_sync(_make_shop(None), _order_node(amount="100.00"))
    assert "platform_fee" not in kwargs["history_comment"]


@pytest.mark.asyncio
async def test_real_create_order_lands_fee_on_the_order_row():
    """End of the chain: the kwarg must actually reach Order.platform_fee. The
    sync tests above mock create_order, so on their own they would still pass if
    the kwarg were computed and then dropped on the floor."""
    from schemas.order import OrderCreate
    from services import order_service

    from models.order import Order

    db = MagicMock()
    added = []
    db.add = MagicMock(side_effect=added.append)
    db.flush = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())

    payload = OrderCreate(
        external_id="777",
        shop_id=uuid4(),
        title="Wallet",
        total_price=100.0,
        currency="USD",
        ordered_at="2026-03-15T10:00:00Z",
        items=[],
        email="b@example.com",
        full_name="T B",
    )
    customer = MagicMock()
    customer.id = uuid4()

    with patch.object(order_service, "upsert_customer", AsyncMock(return_value=customer)):
        await order_service.create_order(
            db, payload, MagicMock(), platform_fee=Decimal("8.00")
        )

    orders = [o for o in added if isinstance(o, Order)]
    assert len(orders) == 1
    assert orders[0].platform_fee == Decimal("8.00")


@pytest.mark.asyncio
async def test_history_comment_fee_is_redacted_for_non_cost_viewers():
    """The token shape is load-bearing: _FINANCIAL_COMMENT_RE must recognise it,
    or the fee leaks to designers through the order timeline, which renders
    import comments verbatim."""
    kwargs = await _run_sync(_make_shop(Decimal("6.50")), _order_node(amount="100.00"))
    redacted = redact_financial_comment(kwargs["history_comment"])
    assert "platform_fee: [redacted]" in redacted
    assert "6.50" not in redacted
