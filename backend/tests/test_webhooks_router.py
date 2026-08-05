"""Shopify webhook router — the second Shopify ingest path.

This file exists because of ORDER-SHIPPING-1 rule 3: the polling sync and the
webhook are independent mappers reading structurally different JSON for the same
order, and "fixed one, forgot the other" is the specific failure that rule names.
The webhook had no tests at all before this sprint, so its half of the mapping
was unguarded.

Router functions are awaited directly with mock sessions, matching the style in
test_shop_fee_router.py — the HMAC and header handling is declarative and cheap
to drive here, so it is covered too.
"""

import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from models.shop import ShopPlatform
from routers.webhooks import shopify_webhook


# ---------- helpers ----------


def _make_shop():
    shop = MagicMock()
    shop.id = uuid4()
    shop.platform = ShopPlatform.SHOPIFY
    shop.shopify_webhook_secret_encrypted = b"enc"
    # Explicit None, not MagicMock's auto-attr: a bare mock reaching
    # compute_platform_fee raises InvalidOperation.
    shop.fee_percent = None
    return shop


def _payload(**overrides):
    """A Shopify orders/create webhook body — REST shape, snake_case, and note
    that only shipping arrives as a money-set. Figures are order 91890_1841's."""
    body = {
        "id": 7410546344092,
        "name": "91890_1841",
        "created_at": "2026-07-30T02:44:55Z",
        "currency": "USD",
        "total_price": "49.50",
        "subtotal_price": "40.50",
        "total_discounts": "4.49",
        "total_tax": "0.00",
        "total_shipping_price_set": {
            "shop_money": {"amount": "9.00", "currency_code": "USD"},
            "presentment_money": {"amount": "9.00", "currency_code": "USD"},
        },
        "shipping_lines": [{"price": "9.00", "discounted_price": "9.00"}],
        "customer": {"first_name": "Nina", "last_name": "Robinson",
                     "email": "nina@example.com"},
        "shipping_address": {"name": "Nina Robinson", "address1": "1 Test St",
                             "country_code": "US"},
        "note": None,
    }
    body.update(overrides)
    return body


def _make_request(body: dict):
    request = MagicMock()
    request.body = AsyncMock(return_value=json.dumps(body).encode())
    return request


def _make_db(shop, *, existing_order=None, system_user=True):
    """Three SELECTs in fixed order: shop, system user, existing order."""
    results = []
    for value in (
        shop,
        MagicMock(id=uuid4()) if system_user else None,
        existing_order,
    ):
        r = MagicMock()
        r.scalar_one_or_none.return_value = value
        results.append(r)

    db = MagicMock()
    db.execute = AsyncMock(side_effect=results)
    return db


async def _post(body, *, topic="orders/create", shop=None, existing_order=None):
    """Drive the webhook and return the create_order mock."""
    shop = shop or _make_shop()
    db = _make_db(shop, existing_order=existing_order)
    with patch("routers.webhooks.verify_shopify_webhook", return_value=True), \
         patch("routers.webhooks.decrypt_value", return_value="secret"), \
         patch("routers.webhooks.create_order", AsyncMock()) as mock_create:
        response = await shopify_webhook(
            shop.id, _make_request(body),
            x_shopify_topic=topic, x_shopify_hmac_sha256="sig", db=db,
        )
    assert response == {"status": "ok"}
    return mock_create


# ---------- auth ----------


@pytest.mark.asyncio
async def test_missing_headers_are_rejected():
    with pytest.raises(HTTPException) as exc:
        await shopify_webhook(
            uuid4(), _make_request({}),
            x_shopify_topic=None, x_shopify_hmac_sha256=None, db=MagicMock(),
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_a_bad_signature_is_rejected():
    shop = _make_shop()
    db = _make_db(shop)
    with patch("routers.webhooks.verify_shopify_webhook", return_value=False), \
         patch("routers.webhooks.decrypt_value", return_value="secret"):
        with pytest.raises(HTTPException) as exc:
            await shopify_webhook(
                shop.id, _make_request(_payload()),
                x_shopify_topic="orders/create", x_shopify_hmac_sha256="wrong", db=db,
            )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_an_unconfigured_shop_is_rejected():
    db = _make_db(None)
    with pytest.raises(HTTPException) as exc:
        await shopify_webhook(
            uuid4(), _make_request(_payload()),
            x_shopify_topic="orders/create", x_shopify_hmac_sha256="sig", db=db,
        )
    assert exc.value.status_code == 404


# ---------- ORDER-SHIPPING-1 mapping ----------


@pytest.mark.asyncio
async def test_webhook_captures_the_breakdown():
    """Rule 3: the same three figures the polling sync captures, read from the
    REST payload's different field names."""
    mock_create = await _post(_payload())
    kwargs = mock_create.await_args.kwargs
    assert kwargs["shipping_revenue"] == Decimal("9.00")
    assert kwargs["discount_total"] == Decimal("4.49")
    assert kwargs["tax_total"] == Decimal("0.00")


@pytest.mark.asyncio
async def test_webhook_and_sync_price_the_same_order_identically():
    """An order landing here instead of on the poll must be priced the same —
    otherwise which path caught it becomes visible in the P&L."""
    from services.shopify_sync import extract_money_breakdown

    mock_create = await _post(_payload())
    webhook = mock_create.await_args.kwargs

    graphql_node = {
        "totalShippingPriceSet": {"shopMoney": {"amount": "9.00"}},
        "totalDiscountsSet": {"shopMoney": {"amount": "4.49"}},
        "totalTaxSet": {"shopMoney": {"amount": "0.00"}},
        "subtotalPriceSet": {"shopMoney": {"amount": "40.50"}},
    }
    sync = extract_money_breakdown(graphql_node)

    for field in ("shipping_revenue", "discount_total", "tax_total"):
        assert webhook[field] == sync[field], field


@pytest.mark.asyncio
async def test_webhook_falls_back_to_shipping_lines():
    body = _payload()
    del body["total_shipping_price_set"]
    mock_create = await _post(body)
    assert mock_create.await_args.kwargs["shipping_revenue"] == Decimal("9.00")


@pytest.mark.asyncio
async def test_webhook_maps_absence_to_none_not_zero():
    """A payload with no shipping figure means UNKNOWN. 0.00 would claim the
    order shipped free."""
    body = _payload()
    for key in ("total_shipping_price_set", "shipping_lines",
                "total_discounts", "total_tax"):
        del body[key]
    mock_create = await _post(body)
    kwargs = mock_create.await_args.kwargs
    assert kwargs["shipping_revenue"] is None
    assert kwargs["discount_total"] is None
    assert kwargs["tax_total"] is None


@pytest.mark.asyncio
async def test_webhook_keeps_a_real_zero():
    """0.00 is a fact ("shipped free"), not absence — it must survive as 0.00 and
    never collapse to None.

    ORDER-SHIPPING-2: the shipping lines are zeroed alongside the money-set. A
    real payload states shipping once, consistently, in both places; overriding
    only the money-set built a body Shopify would never send, and now that the
    mapper reads the lines first it was the lines' 9.00 being asserted against.
    """
    body = _payload(total_shipping_price_set={"shop_money": {"amount": "0.00"}},
                    shipping_lines=[{"price": "0.00", "discounted_price": "0.00"}],
                    total_price="40.50")
    mock_create = await _post(body)
    assert mock_create.await_args.kwargs["shipping_revenue"] == Decimal("0.00")
    assert mock_create.await_args.kwargs["shipping_discount"] == Decimal("0.00")


@pytest.mark.asyncio
async def test_webhook_creates_an_unbalanced_order_anyway():
    """Store anyway and flag, same rule as the sync."""
    mock_create = await _post(_payload(subtotal_price="35.00"))
    assert mock_create.await_count == 1
    assert mock_create.await_args.kwargs["shipping_revenue"] == Decimal("9.00")


# ---------- existing-order behaviour (unchanged this sprint) ----------


@pytest.mark.asyncio
async def test_an_existing_order_is_still_a_no_op():
    """orders/updated no-ops on a row that already exists, and ORDER-SHIPPING-1
    deliberately did not change that: refreshing these three would also mean
    deciding what to do about total_price (BUG-4), which is out of scope. The
    backfill is the re-sync path, and it reports drift rather than writing it."""
    mock_create = await _post(
        _payload(), topic="orders/updated", existing_order=MagicMock(),
    )
    mock_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unhandled_topic_is_ignored():
    mock_create = await _post(_payload(), topic="products/create")
    mock_create.assert_not_awaited()
