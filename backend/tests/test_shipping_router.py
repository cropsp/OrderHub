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


def _make_user(role=UserRole.OWNER):
    # USER-ACCESS-1: default to OWNER so the shop-access guard is a no-op — these
    # tests exercise TTN mechanics, not access control (covered by dedicated tests).
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
    packaging_id=None,
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
    order.packaging_id = packaging_id
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
         patch("routers.shipping.change_order_status", AsyncMock(return_value=(MagicMock(), []))) as mock_status:
        result = await create_np_ttn(
            order_id=order.id,
            body=_ttn_body(),
            current_user=user,
            db=db,
        )

    assert result == {"status": "success", "ttn": "20450123456789", "warnings": []}
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
         patch("routers.shipping.change_order_status", AsyncMock(return_value=(MagicMock(), []))) as mock_status:
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


# ---------------------------------------------------------------------------
# WH-2: the TTN no longer touches stock at all
#
# PKG-2 used to decrement packaging here on create and refund it on delete. Both
# calls are gone: consumption is anchored to the SHIPPED transition, which the
# create path triggers through change_order_status and the delete path reverses
# WITHOUT giving anything back. These tests are the regression guard against
# someone re-introducing a second stock trigger on label churn.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_ttn_moves_no_stock_itself():
    """Creating a label writes no ledger row of its own. The only stock effect is
    whatever the SHIPPED transition books, and it arrives through the status hook."""
    shop = _make_shop(sender_ref="sender-ref-1", contact_ref="sender-contact-1")
    order = _make_order(shop=shop, packaging_id=uuid.uuid4())
    user = _make_user()

    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()

    fake_client = MagicMock()
    fake_client.get_counterparties = AsyncMock(return_value=[{"Ref": "rec-ref-1"}])
    fake_client.get_contact_persons = AsyncMock(return_value=[{"Ref": "rec-contact-1"}])
    fake_client.create_internet_document = AsyncMock(return_value={
        "IntDocNumber": "20450123456789",
        "Ref": "ttn-ref-1",
    })

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)), \
         patch("routers.shipping.decrypt_value", return_value="plain-key"), \
         patch("routers.shipping.NovaPoshtaClient", return_value=fake_client), \
         patch("routers.shipping.change_order_status", AsyncMock(return_value=(MagicMock(), []))) as mock_status:
        result = await create_np_ttn(
            order_id=order.id,
            body=_ttn_body(),
            current_user=user,
            db=db,
        )

    assert result == {"status": "success", "ttn": "20450123456789", "warnings": []}
    db.add.assert_not_called(), "the router itself stages no ledger row"
    # The one and only stock path: SHIPPED.
    mock_status.assert_awaited_once()
    assert mock_status.await_args.args[2] == OrderStatus.SHIPPED


@pytest.mark.asyncio
async def test_create_ttn_forwards_consumption_warnings():
    """Warnings now come from the consumption hook alone — packaging warnings
    included, since the box is consumed inside that same transition."""
    shop = _make_shop(sender_ref="sender-ref-1", contact_ref="sender-contact-1")
    order = _make_order(shop=shop, packaging_id=uuid.uuid4())

    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    fake_client = MagicMock()
    fake_client.get_counterparties = AsyncMock(return_value=[{"Ref": "rec-ref-1"}])
    fake_client.get_contact_persons = AsyncMock(return_value=[{"Ref": "rec-contact-1"}])
    fake_client.create_internet_document = AsyncMock(return_value={
        "IntDocNumber": "20450123456789",
        "Ref": "ttn-ref-1",
    })

    warning_msg = "⚠ Stock for «Коробка 100×120×50» went negative. Time to restock."
    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)), \
         patch("routers.shipping.decrypt_value", return_value="plain-key"), \
         patch("routers.shipping.NovaPoshtaClient", return_value=fake_client), \
         patch(
             "routers.shipping.change_order_status",
             AsyncMock(return_value=(MagicMock(), [warning_msg])),
         ):
        result = await create_np_ttn(
            order_id=order.id,
            body=_ttn_body(),
            current_user=_make_user(),
            db=db,
        )

    assert result["warnings"] == [warning_msg]


@pytest.mark.asyncio
async def test_create_ttn_on_an_already_shipped_order_does_not_re_consume():
    """The status guard is what makes a re-issued label free: an order already in
    SHIPPED never re-enters change_order_status, so nothing is consumed twice."""
    shop = _make_shop(sender_ref="sender-ref-1", contact_ref="sender-contact-1")
    order = _make_order(shop=shop, packaging_id=uuid.uuid4())
    order.status = OrderStatus.SHIPPED

    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    fake_client = MagicMock()
    fake_client.get_counterparties = AsyncMock(return_value=[{"Ref": "rec-ref-1"}])
    fake_client.get_contact_persons = AsyncMock(return_value=[{"Ref": "rec-contact-1"}])
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
            current_user=_make_user(),
            db=db,
        )

    assert result["warnings"] == []
    mock_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_ttn_moves_no_stock_itself():
    """Deleting a label gives nothing back. The +1 refund PKG-2 wrote here was the
    mirror of a decrement that no longer happens; keeping it would credit a box
    that was never taken, and the parcel was still packed."""
    order = _make_order(ttn="20450999999999", packaging_id=uuid.uuid4())

    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()

    fake_client = MagicMock()
    fake_client.delete_internet_document = AsyncMock(return_value=True)

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)), \
         patch("routers.shipping.decrypt_value", return_value="plain-key"), \
         patch("routers.shipping.NovaPoshtaClient", return_value=fake_client), \
         patch("routers.shipping.change_order_status", AsyncMock(return_value=(MagicMock(), []))) as mock_status:
        await delete_np_ttn(
            order_id=order.id,
            current_user=_make_user(),
            db=db,
        )

    db.add.assert_not_called()
    # Status still reverts — only the stock give-back is gone.
    assert mock_status.await_args.args[2] == OrderStatus.IN_PRODUCTION


@pytest.mark.asyncio
async def test_create_ttn_rolls_back_on_np_failure():
    """NP API failure → the whole transaction rolls back, TTN included."""
    shop = _make_shop(sender_ref="sender-ref-1", contact_ref="sender-contact-1")
    order = _make_order(shop=shop, packaging_id=uuid.uuid4())

    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    fake_client = MagicMock()
    fake_client.get_counterparties = AsyncMock(return_value=[{"Ref": "rec-ref-1"}])
    fake_client.get_contact_persons = AsyncMock(return_value=[{"Ref": "rec-contact-1"}])
    fake_client.create_internet_document = AsyncMock(side_effect=RuntimeError("NP down"))

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)), \
         patch("routers.shipping.decrypt_value", return_value="plain-key"), \
         patch("routers.shipping.NovaPoshtaClient", return_value=fake_client), \
         patch("routers.shipping.change_order_status", AsyncMock(return_value=(MagicMock(), []))) as mock_status:
        with pytest.raises(HTTPException):
            await create_np_ttn(
                order_id=order.id,
                body=_ttn_body(),
                current_user=_make_user(),
                db=db,
            )

    # The NP call raises before the status transition, so nothing was consumed.
    mock_status.assert_not_awaited()
    db.rollback.assert_awaited()
    db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# NP-UX-2: idempotent delete (soft-success on "already deleted" / "not found")
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_ttn_soft_success_when_np_says_already_deleted():
    """NP-UX-2: NP returns the exact 'Document already deleted ...' message that
    NP-FIX-4 Phase A documented. Handler must clear the local ttn and return
    status='soft_success' instead of HTTP 400.
    """
    from services.nova_poshta import NovaPoshtaAPIError

    box_id = uuid.uuid4()
    order = _make_order(ttn="20451436562514", packaging_id=box_id)

    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    fake_client = MagicMock()
    fake_client.delete_internet_document = AsyncMock(
        side_effect=NovaPoshtaAPIError(
            "[NP API] Error: Document already deleted 20451436562514, No document changed DeletionMark"
        )
    )

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)), \
         patch("routers.shipping.decrypt_value", return_value="plain-key"), \
         patch("routers.shipping.NovaPoshtaClient", return_value=fake_client), \
         patch("routers.shipping.change_order_status", AsyncMock(return_value=(MagicMock(), []))) as mock_status:
        result = await delete_np_ttn(
            order_id=order.id,
            current_user=_make_user(),
            db=db,
        )

    assert result["status"] == "soft_success"
    assert "already deleted" in result["message"].lower()
    assert order.ttn_number is None
    db.commit.assert_awaited_once()
    db.rollback.assert_not_called()

    # Audit comment must distinguish soft-success from real success.
    status_args = mock_status.await_args.args
    assert status_args[2] == OrderStatus.IN_PRODUCTION
    assert "already deleted on NP side" in status_args[4]


@pytest.mark.asyncio
async def test_delete_ttn_soft_success_when_np_says_no_document_found():
    """NP-UX-2: 'No document found' substring also maps to soft-success."""
    from services.nova_poshta import NovaPoshtaAPIError

    order = _make_order(ttn="20450999999999")

    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    fake_client = MagicMock()
    fake_client.delete_internet_document = AsyncMock(
        side_effect=NovaPoshtaAPIError("[NP API] Error: No document found")
    )

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)), \
         patch("routers.shipping.decrypt_value", return_value="plain-key"), \
         patch("routers.shipping.NovaPoshtaClient", return_value=fake_client), \
         patch("routers.shipping.change_order_status", AsyncMock(return_value=(MagicMock(), []))):
        result = await delete_np_ttn(
            order_id=order.id,
            current_user=_make_user(),
            db=db,
        )

    assert result["status"] == "soft_success"
    assert order.ttn_number is None


@pytest.mark.asyncio
async def test_delete_ttn_unmatched_np_error_still_400():
    """NP-UX-2 regression guard: NP errors that don't match the soft-success
    patterns (e.g. auth failure, permission denied) must still raise HTTP 400
    with rollback — only the specific 'already gone' messages get the soft path.
    """
    from services.nova_poshta import NovaPoshtaAPIError

    order = _make_order(ttn="20450999999999", packaging_id=uuid.uuid4())

    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    fake_client = MagicMock()
    fake_client.delete_internet_document = AsyncMock(
        side_effect=NovaPoshtaAPIError("[NP API] Error: API key is invalid")
    )

    with patch("routers.shipping.get_order_detail", AsyncMock(return_value=order)), \
         patch("routers.shipping.decrypt_value", return_value="plain-key"), \
         patch("routers.shipping.NovaPoshtaClient", return_value=fake_client), \
         patch("routers.shipping.change_order_status", AsyncMock(return_value=(MagicMock(), []))):
        with pytest.raises(HTTPException) as exc:
            await delete_np_ttn(
                order_id=order.id,
                current_user=_make_user(),
                db=db,
            )

    assert exc.value.status_code == 400
    db.rollback.assert_awaited()
    db.commit.assert_not_called()
    # Local state preserved on hard failure.
    assert order.ttn_number == "20450999999999"
