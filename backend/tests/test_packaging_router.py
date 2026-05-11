"""PKG-2 — Router-level tests for packaging endpoints.

Covers:
- POST /packaging-boxes/{id}/restock happy path
- Validation: quantity must be >= 1
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from models.stock_movement import StockMovementReason
from models.user import UserRole
from routers.packaging import restock_packaging
from schemas.packaging import RestockRequest


def _make_user(role=UserRole.OWNER):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


@pytest.mark.asyncio
async def test_restock_packaging_happy_path():
    box_id = uuid.uuid4()
    box = MagicMock()
    box.id = box_id
    box.name = "Box M"
    box.stock_quantity = 15
    box.low_stock_threshold = 5

    db = MagicMock()
    db.commit = AsyncMock()
    db.get = AsyncMock(return_value=box)

    user = _make_user()
    body = RestockRequest(quantity=10, note="shelf count")

    with patch(
        "routers.packaging.stock_service.apply_movement",
        AsyncMock(return_value=[]),
    ) as mock_apply:
        result = await restock_packaging(
            box_id=box_id,
            body=body,
            db=db,
            user=user,
        )

    mock_apply.assert_awaited_once()
    kwargs = mock_apply.await_args.kwargs
    assert kwargs["box_id"] == box_id
    assert kwargs["delta"] == 10
    assert kwargs["reason"] == StockMovementReason.RESTOCK
    assert kwargs["user_id"] == user.id
    assert kwargs["note"] == "shelf count"

    db.commit.assert_awaited_once()
    assert result is box


def test_restock_request_rejects_zero_quantity():
    with pytest.raises(ValidationError):
        RestockRequest(quantity=0)


def test_restock_request_rejects_negative_quantity():
    with pytest.raises(ValidationError):
        RestockRequest(quantity=-3)


def test_restock_request_allows_minimum_one():
    body = RestockRequest(quantity=1)
    assert body.quantity == 1
    assert body.note is None
