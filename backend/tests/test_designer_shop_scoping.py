"""USER-ACCESS-1 — grant-based shop access via get_shop_for_user.

Supersedes the SEC-05 assignment-in-shop rule: shop access is now an explicit
`user_shop_access` grant. OWNER is unrestricted; MANAGER and DESIGNER need a
grant (a designer's grant is materialised when an order is assigned to them).
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


def _grant_result(shop_ids):
    """Mimics `db.execute(select(UserShopAccess.shop_id))` in get_shop_scope."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = list(shop_ids)
    return r


@pytest.mark.asyncio
async def test_designer_with_grant_gets_access():
    shop_id = uuid4()
    shop = _make_shop(shop_id)
    designer = _make_user(UserRole.DESIGNER)

    db = AsyncMock()
    db.execute.side_effect = [_shop_result(shop), _grant_result([shop_id])]

    result = await get_shop_for_user(shop_id=shop_id, db=db, current_user=designer)
    assert result is shop


@pytest.mark.asyncio
async def test_designer_without_grant_gets_403():
    shop_id = uuid4()
    shop = _make_shop(shop_id)
    designer = _make_user(UserRole.DESIGNER)

    db = AsyncMock()
    db.execute.side_effect = [_shop_result(shop), _grant_result([])]

    with pytest.raises(HTTPException) as exc:
        await get_shop_for_user(shop_id=shop_id, db=db, current_user=designer)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_manager_with_grant_gets_access():
    shop_id = uuid4()
    shop = _make_shop(shop_id)
    manager = _make_user(UserRole.MANAGER)

    db = AsyncMock()
    db.execute.side_effect = [_shop_result(shop), _grant_result([shop_id])]

    result = await get_shop_for_user(shop_id=shop_id, db=db, current_user=manager)
    assert result is shop


@pytest.mark.asyncio
async def test_manager_without_grant_gets_403():
    """Behaviour change from SEC-05: managers are no longer globally unrestricted."""
    shop_id = uuid4()
    shop = _make_shop(shop_id)
    manager = _make_user(UserRole.MANAGER)

    db = AsyncMock()
    db.execute.side_effect = [_shop_result(shop), _grant_result([uuid4()])]

    with pytest.raises(HTTPException) as exc:
        await get_shop_for_user(shop_id=shop_id, db=db, current_user=manager)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_owner_is_unrestricted_without_grant_query():
    shop_id = uuid4()
    shop = _make_shop(shop_id)
    owner = _make_user(UserRole.OWNER)

    db = AsyncMock()
    db.execute.side_effect = [_shop_result(shop)]

    result = await get_shop_for_user(shop_id=shop_id, db=db, current_user=owner)
    assert result is shop
    # OWNER short-circuits — only the shop lookup runs, never a grant query.
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_missing_shop_returns_404():
    shop_id = uuid4()
    designer = _make_user(UserRole.DESIGNER)

    db = AsyncMock()
    db.execute.side_effect = [_shop_result(None)]

    with pytest.raises(HTTPException) as exc:
        await get_shop_for_user(shop_id=shop_id, db=db, current_user=designer)
    assert exc.value.status_code == 404
