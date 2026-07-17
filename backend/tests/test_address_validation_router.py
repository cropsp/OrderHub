"""ADDR-VAL-1 — Router tests for POST /api/orders/{order_id}/validate-address.

Calls the endpoint coroutine directly (mirroring test_shipping_router.py and
test_orders_router.py) — no TestClient, no AsyncClient. The service is mocked at the
router's import boundary; the coverage gate itself is covered in
test_address_validation.py.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models.order import AddressValidationStatus
from models.user import UserRole
from routers.orders import validate_order_address
from schemas.address_validation import AddressVerdict


def _make_user(role=UserRole.OWNER, user_id=None):
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.role = role
    user.email = "someone@example.com"
    return user


def _make_order(country="GB", designer_id=None):
    order = MagicMock()
    order.id = uuid.uuid4()
    order.shipping_street_1 = "12 Example Road"
    order.shipping_street_2 = None
    order.shipping_city = "London"
    order.shipping_state = None
    order.shipping_zip = "RM6 4TJ"
    order.shipping_country = country
    order.assigned_designer_id = designer_id
    order.address_validation_status = None
    order.address_validation_at = None
    return order


def _verdict(status):
    return AddressVerdict(
        status=status, message="m", validated_at=datetime.now(timezone.utc)
    )


@pytest.mark.asyncio
async def test_returns_404_when_order_missing():
    db = AsyncMock()
    with patch("routers.orders.get_order_detail", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await validate_order_address(uuid.uuid4(), _make_user(), db)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_designer_not_assigned_to_order_gets_403():
    db = AsyncMock()
    order = _make_order(designer_id=uuid.uuid4())  # someone else
    designer = _make_user(role=UserRole.DESIGNER)

    with patch("routers.orders.get_order_detail", new=AsyncMock(return_value=order)):
        with pytest.raises(HTTPException) as exc:
            await validate_order_address(order.id, designer, db)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_assigned_designer_is_allowed():
    db = AsyncMock()
    designer = _make_user(role=UserRole.DESIGNER)
    order = _make_order(designer_id=designer.id)

    with patch("routers.orders.get_order_detail", new=AsyncMock(return_value=order)):
        with patch(
            "routers.orders.validate_address",
            new=AsyncMock(return_value=_verdict(AddressValidationStatus.VERIFIED)),
        ):
            result = await validate_order_address(order.id, designer, db)

    assert result.status is AddressValidationStatus.VERIFIED


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.OWNER, UserRole.MANAGER])
async def test_owner_and_manager_are_allowed(role):
    db = AsyncMock()
    order = _make_order()

    with patch("routers.orders.get_order_detail", new=AsyncMock(return_value=order)):
        with patch(
            "routers.orders.validate_address",
            new=AsyncMock(return_value=_verdict(AddressValidationStatus.VERIFIED)),
        ):
            result = await validate_order_address(order.id, _make_user(role=role), db)

    assert result.status is AddressValidationStatus.VERIFIED


@pytest.mark.asyncio
async def test_shipping_fields_are_passed_through_to_the_service():
    db = AsyncMock()
    order = _make_order()

    with patch("routers.orders.get_order_detail", new=AsyncMock(return_value=order)):
        with patch(
            "routers.orders.validate_address",
            new=AsyncMock(return_value=_verdict(AddressValidationStatus.VERIFIED)),
        ) as service:
            await validate_order_address(order.id, _make_user(), db)

    address = service.await_args.args[1]
    assert address.street_1 == "12 Example Road"
    assert address.city == "London"
    assert address.zip == "RM6 4TJ"
    assert address.country == "GB"


# ─── Persistence ─────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("status", [
    AddressValidationStatus.VERIFIED,
    AddressValidationStatus.NEEDS_ATTENTION,
    AddressValidationStatus.COULDNT_VERIFY,
    AddressValidationStatus.UNSUPPORTED,
    AddressValidationStatus.UA,
])
async def test_real_outcomes_are_persisted(status):
    db = AsyncMock()
    order = _make_order()
    verdict = _verdict(status)

    with patch("routers.orders.get_order_detail", new=AsyncMock(return_value=order)):
        with patch("routers.orders.validate_address", new=AsyncMock(return_value=verdict)):
            await validate_order_address(order.id, _make_user(), db)

    assert order.address_validation_status is status
    assert order.address_validation_at == verdict.validated_at
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_unavailable_is_not_persisted_and_does_not_clobber_a_prior_verdict():
    """A transient outage must not erase a previously good verdict."""
    db = AsyncMock()
    order = _make_order()
    earlier = datetime(2026, 7, 1, tzinfo=timezone.utc)
    order.address_validation_status = AddressValidationStatus.VERIFIED
    order.address_validation_at = earlier

    with patch("routers.orders.get_order_detail", new=AsyncMock(return_value=order)):
        with patch(
            "routers.orders.validate_address",
            new=AsyncMock(return_value=_verdict(AddressValidationStatus.UNAVAILABLE)),
        ):
            result = await validate_order_address(order.id, _make_user(), db)

    assert result.status is AddressValidationStatus.UNAVAILABLE
    assert order.address_validation_status is AddressValidationStatus.VERIFIED
    assert order.address_validation_at == earlier
    db.commit.assert_not_awaited()
