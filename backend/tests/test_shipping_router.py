"""NP-FIX-2 — Router-level tests for the four shipping endpoints.

Calls endpoint coroutines directly (mirroring test_designer_shop_scoping.py
and test_products_platform_gate.py) — no TestClient, no AsyncClient. Mocks
NovaPoshtaClient, decrypt_value, get_order_detail, and change_order_status
at the routers.shipping import boundary so no real HTTP and no real DB.
"""
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models.order import OrderStatus
from models.user import UserRole
from routers.shipping import (
    CreateTTNRequest,
    create_np_ttn,
    delete_np_ttn,
    get_warehouses,
    search_cities,
)


def _make_user(role=UserRole.MANAGER):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


def _make_shop(*, np_key="enc-key", sender_ref=None, contact_ref=None):
    shop = MagicMock()
    shop.id = uuid.uuid4()
    shop.np_api_key_encrypted = np_key
    shop.np_sender_ref = sender_ref
    shop.np_sender_contact_ref = contact_ref
    shop.np_sender_city_ref = "city-sender-ref"
    shop.np_sender_warehouse_ref = "wh-sender-ref"
    shop.np_sender_phone = "380501112233"
    shop.np_default_payer_type = "Sender"
    shop.np_default_payment_method = "Cash"
    shop.np_default_volume_m3 = 0.004
    shop.np_default_weight_kg = 0.5
    shop.np_default_description = "Leather goods"
    return shop


def _make_order(
    *,
    ttn=None,
    shop=None,
    shipping_city="Київ",
    shipping_name="Петренко Іван Сергійович",
    shipping_phone="0501234567",
    shipping_city_ref="city-recipient-ref",
    shipping_warehouse_ref="wh-recipient-ref",
    status=OrderStatus.IN_PRODUCTION,
):
    order = MagicMock()
    order.id = uuid.uuid4()
    order.ttn_number = ttn
    order.shop = shop if shop is not None else _make_shop()
    order.shipping_city = shipping_city
    order.shipping_name = shipping_name
    order.shipping_phone = shipping_phone
    order.shipping_city_ref = shipping_city_ref
    order.shipping_warehouse_ref = shipping_warehouse_ref
    order.status = status
    order.parcel_override = False
    order.total_price = Decimal("1500")
    order.external_id = "EXT-1001"
    return order


def _shop_result(shop):
    r = MagicMock()
    r.scalar_one_or_none.return_value = shop
    return r


def _ttn_body(**overrides):
    return CreateTTNRequest(**overrides)


# ---------------------------------------------------------------------------
# GET /cities
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_cities_returns_400_when_no_np_shop_configured():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_shop_result(None))

    with pytest.raises(HTTPException) as exc:
        await search_cities(query="Ки", current_user=_make_user(), db=db)

    assert exc.value.status_code == 400
    assert "No shop with Nova Poshta API key found" in exc.value.detail


@pytest.mark.asyncio
async def test_search_cities_returns_results_from_np_client():
    shop = _make_shop()
    db = MagicMock()
    db.execute = AsyncMock(return_value=_shop_result(shop))

    fake_cities = [{"Description": "Київ", "Ref": "city-1"}]
    fake_client = MagicMock()
    fake_client.get_cities = AsyncMock(return_value=fake_cities)

    with patch("routers.shipping.decrypt_value", return_value="plain-key"), \
         patch("routers.shipping.NovaPoshtaClient", return_value=fake_client):
        result = await search_cities(query="Київ", current_user=_make_user(), db=db)

    assert result == fake_cities
    fake_client.get_cities.assert_awaited_once_with("Київ")


# ---------------------------------------------------------------------------
# GET /warehouses/{city_ref}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_warehouses_returns_400_when_no_np_shop_configured():
    db = MagicMock()
    db.execute = AsyncMock(return_value=_shop_result(None))

    with pytest.raises(HTTPException) as exc:
        await get_warehouses(city_ref="city-1", query="", current_user=_make_user(), db=db)

    assert exc.value.status_code == 400
    assert "No shop with Nova Poshta API key found" in exc.value.detail


# ---------------------------------------------------------------------------
# POST /np-ttn/{order_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_ttn_returns_404_when_order_not_found():
    db = MagicMock()
    user = _make_user()

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await create_np_ttn(
                order_id=uuid.uuid4(),
                body=_ttn_body(),
                current_user=user,
                db=db,
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Order not found"


@pytest.mark.asyncio
async def test_create_ttn_returns_400_when_order_already_has_ttn():
    db = MagicMock()
    order = _make_order(ttn="20450000000001")

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)):
        with pytest.raises(HTTPException) as exc:
            await create_np_ttn(
                order_id=order.id,
                body=_ttn_body(),
                current_user=_make_user(),
                db=db,
            )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Order already has a TTN"


@pytest.mark.asyncio
async def test_create_ttn_returns_400_when_shop_has_no_np_key():
    db = MagicMock()
    shop = _make_shop(np_key=None)
    order = _make_order(shop=shop)

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)):
        with pytest.raises(HTTPException) as exc:
            await create_np_ttn(
                order_id=order.id,
                body=_ttn_body(),
                current_user=_make_user(),
                db=db,
            )

    assert exc.value.status_code == 400
    assert "Nova Poshta configured" in exc.value.detail


@pytest.mark.asyncio
async def test_create_ttn_returns_400_when_recipient_data_missing():
    db = MagicMock()
    order = _make_order(shipping_city=None)

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)):
        with pytest.raises(HTTPException) as exc:
            await create_np_ttn(
                order_id=order.id,
                body=_ttn_body(),
                current_user=_make_user(),
                db=db,
            )

    assert exc.value.status_code == 400
    assert "missing required shipping information" in exc.value.detail


@pytest.mark.asyncio
async def test_create_ttn_returns_400_when_recipient_warehouse_ref_missing():
    db = MagicMock()
    order = _make_order(shipping_warehouse_ref=None)

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)):
        with pytest.raises(HTTPException) as exc:
            await create_np_ttn(
                order_id=order.id,
                body=_ttn_body(),
                current_user=_make_user(),
                db=db,
            )

    assert exc.value.status_code == 400
    assert "Nova Poshta city or warehouse reference" in exc.value.detail


@pytest.mark.asyncio
async def test_create_ttn_returns_400_when_sender_city_ref_missing():
    """NP-FIX-1: shop with API key but no sender city ref → 400 before any NP call."""
    db = MagicMock()
    shop = _make_shop()
    shop.np_sender_city_ref = None
    order = _make_order(shop=shop)

    np_client_cls = MagicMock()

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)), \
         patch("routers.shipping.NovaPoshtaClient", np_client_cls):
        with pytest.raises(HTTPException) as exc:
            await create_np_ttn(
                order_id=order.id,
                body=_ttn_body(),
                current_user=_make_user(),
                db=db,
            )

    assert exc.value.status_code == 400
    assert "sender warehouse is not configured" in exc.value.detail
    np_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_create_ttn_returns_400_when_sender_warehouse_ref_missing():
    """NP-FIX-1: shop with API key but no sender warehouse ref → 400 before any NP call."""
    db = MagicMock()
    shop = _make_shop()
    shop.np_sender_warehouse_ref = None
    order = _make_order(shop=shop)

    np_client_cls = MagicMock()

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)), \
         patch("routers.shipping.NovaPoshtaClient", np_client_cls):
        with pytest.raises(HTTPException) as exc:
            await create_np_ttn(
                order_id=order.id,
                body=_ttn_body(),
                current_user=_make_user(),
                db=db,
            )

    assert exc.value.status_code == 400
    assert "sender warehouse is not configured" in exc.value.detail
    np_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_create_ttn_happy_path_with_cached_sender_refs():
    """Shop has cached sender refs → skips sender NP calls. Recipient is found
    via get_counterparties (existing). create_internet_document returns TTN.
    """
    shop = _make_shop(sender_ref="sender-ref-1", contact_ref="sender-contact-1")
    order = _make_order(shop=shop)
    user = _make_user()

    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    fake_client = MagicMock()
    fake_client.get_counterparties = AsyncMock(return_value=[
        {"Ref": "rec-ref-1"},
    ])
    fake_client.get_contact_persons = AsyncMock(return_value=[
        {"Ref": "rec-contact-1"},
    ])
    fake_client.create_internet_document = AsyncMock(return_value={
        "IntDocNumber": "20450123456789",
        "Ref": "ttn-ref-1",
    })

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)), \
         patch("routers.shipping.decrypt_value", return_value="plain-key"), \
         patch("routers.shipping.NovaPoshtaClient", return_value=fake_client), \
         patch("routers.shipping.change_order_status", AsyncMock()) as mock_status:
        result = await create_np_ttn(
            order_id=order.id,
            body=_ttn_body(),
            current_user=user,
            db=db,
        )

    assert result == {"status": "success", "ttn": "20450123456789"}
    assert order.ttn_number == "20450123456789"

    # Cached refs path → no calls to get sender info, but recipient lookup runs.
    fake_client.get_counterparties.assert_awaited_once()
    args, kwargs = fake_client.get_counterparties.await_args
    assert args[0] == "Recipient"

    fake_client.create_internet_document.assert_awaited_once()
    db.commit.assert_awaited()

    # Order was IN_PRODUCTION → status flips to SHIPPED.
    mock_status.assert_awaited_once()
    status_args = mock_status.await_args.args
    assert status_args[2] == OrderStatus.SHIPPED


# ---------------------------------------------------------------------------
# DELETE /np-ttn/{order_id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_ttn_returns_404_when_order_not_found():
    db = MagicMock()

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await delete_np_ttn(
                order_id=uuid.uuid4(),
                current_user=_make_user(),
                db=db,
            )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Order not found"


@pytest.mark.asyncio
async def test_delete_ttn_returns_400_when_order_has_no_ttn():
    db = MagicMock()
    order = _make_order(ttn=None)

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)):
        with pytest.raises(HTTPException) as exc:
            await delete_np_ttn(
                order_id=order.id,
                current_user=_make_user(),
                db=db,
            )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Order does not have a TTN"


@pytest.mark.asyncio
async def test_delete_ttn_happy_path():
    order = _make_order(ttn="20450999999999")

    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    fake_client = MagicMock()
    fake_client.delete_internet_document = AsyncMock(return_value=True)

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)), \
         patch("routers.shipping.decrypt_value", return_value="plain-key"), \
         patch("routers.shipping.NovaPoshtaClient", return_value=fake_client), \
         patch("routers.shipping.change_order_status", AsyncMock()) as mock_status:
        result = await delete_np_ttn(
            order_id=order.id,
            current_user=_make_user(),
            db=db,
        )

    assert result["status"] == "success"
    assert "20450999999999" in result["message"]
    assert order.ttn_number is None
    fake_client.delete_internet_document.assert_awaited_once_with("20450999999999")

    mock_status.assert_awaited_once()
    status_args = mock_status.await_args.args
    assert status_args[2] == OrderStatus.IN_PRODUCTION
