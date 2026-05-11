"""PKG-1 / PKG-1b — packaging_id validation on order update.

The PATCH /api/orders/{id} flows through services.order_service.update_order.
These tests cover the packaging_id paths in that service:
  1. happy path — supplied packaging exists -> set
  2. null clear — packaging_id=None unsets a previous selection
  3. unknown-box reject — packaging not found -> 400

The cross-shop reject case (PKG-1) was removed in PKG-1b when
PackagingBox.shop_id was dropped (shared inventory model).
"""
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from services.order_service import update_order
from schemas.order import OrderUpdate
from models.user import UserRole
from models.order import OrderStatus


def _make_user(role=UserRole.OWNER):
    user = MagicMock()
    user.id = uuid4()
    user.role = role
    return user


def _make_order(shop_id, packaging_id=None):
    order = MagicMock()
    order.id = uuid4()
    order.shop_id = shop_id
    order.customer_id = uuid4()
    order.status = OrderStatus.NEW
    order.packaging_id = packaging_id
    return order


def _make_box(box_id):
    box = MagicMock()
    box.id = box_id
    return box


@pytest.mark.asyncio
async def test_update_order_sets_packaging_id_happy_path():
    shop_id = uuid4()
    box_id = uuid4()
    order = _make_order(shop_id)
    box = _make_box(box_id)
    user = _make_user(UserRole.OWNER)

    db = AsyncMock()
    db.get.return_value = box

    payload = OrderUpdate(packaging_id=box_id)
    result = await update_order(db, order, payload, user)

    assert result.packaging_id == box_id
    db.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_order_null_clears_packaging_id():
    shop_id = uuid4()
    previous_box_id = uuid4()
    order = _make_order(shop_id, packaging_id=previous_box_id)
    user = _make_user(UserRole.OWNER)

    db = AsyncMock()

    payload = OrderUpdate(packaging_id=None)
    result = await update_order(db, order, payload, user)

    assert result.packaging_id is None
    # null path must not look up the box
    db.get.assert_not_called()


@pytest.mark.asyncio
async def test_update_order_unknown_packaging_rejected():
    shop_id = uuid4()
    order = _make_order(shop_id)
    user = _make_user(UserRole.OWNER)

    db = AsyncMock()
    db.get.return_value = None  # box not found

    payload = OrderUpdate(packaging_id=uuid4())
    with pytest.raises(HTTPException) as exc:
        await update_order(db, order, payload, user)
    assert exc.value.status_code == 400
