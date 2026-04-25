"""SEC-05 — Designer shop access scoping.

Verifies get_shop_for_user enforces that designers can only access shops where
they have at least one assigned order. Owner/manager roles are unaffected.
"""
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from routers.dependencies import get_shop_for_user
from models.user import UserRole


def _make_shop(shop_id):
    shop = MagicMock()
    shop.id = shop_id
    return shop


def _make_user(role, user_id=None):
    user = MagicMock()
    user.id = user_id or uuid4()
    user.role = role
    return user


def _shop_result(shop):
    r = MagicMock()
    r.scalar_one_or_none.return_value = shop
    return r


def _assignment_result(found):
    r = MagicMock()
    r.scalar_one_or_none.return_value = uuid4() if found else None
    return r


@pytest.mark.asyncio
async def test_designer_with_assignment_in_shop_gets_access():
    shop_id = uuid4()
    shop = _make_shop(shop_id)
    designer = _make_user(UserRole.DESIGNER)

    db = AsyncMock()
    db.execute.side_effect = [_shop_result(shop), _assignment_result(True)]

    result = await get_shop_for_user(shop_id=shop_id, db=db, current_user=designer)
    assert result is shop


@pytest.mark.asyncio
async def test_designer_without_assignment_in_shop_gets_403():
    shop_id = uuid4()
    shop = _make_shop(shop_id)
    designer = _make_user(UserRole.DESIGNER)

    db = AsyncMock()
    db.execute.side_effect = [_shop_result(shop), _assignment_result(False)]

    with pytest.raises(HTTPException) as exc:
        await get_shop_for_user(shop_id=shop_id, db=db, current_user=designer)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_owner_does_not_require_assignment():
    shop_id = uuid4()
    shop = _make_shop(shop_id)
    owner = _make_user(UserRole.OWNER)

    db = AsyncMock()
    db.execute.side_effect = [_shop_result(shop)]

    result = await get_shop_for_user(shop_id=shop_id, db=db, current_user=owner)
    assert result is shop
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_manager_does_not_require_assignment():
    shop_id = uuid4()
    shop = _make_shop(shop_id)
    manager = _make_user(UserRole.MANAGER)

    db = AsyncMock()
    db.execute.side_effect = [_shop_result(shop)]

    result = await get_shop_for_user(shop_id=shop_id, db=db, current_user=manager)
    assert result is shop


@pytest.mark.asyncio
async def test_missing_shop_returns_404():
    shop_id = uuid4()
    designer = _make_user(UserRole.DESIGNER)

    db = AsyncMock()
    db.execute.side_effect = [_shop_result(None)]

    with pytest.raises(HTTPException) as exc:
        await get_shop_for_user(shop_id=shop_id, db=db, current_user=designer)
    assert exc.value.status_code == 404
