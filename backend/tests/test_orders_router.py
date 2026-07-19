"""PKG-1 / PKG-1b — packaging_id validation on order update.

The PATCH /api/orders/{id} flows through services.order_service.update_order.
These tests cover the packaging_id paths in that service:
  1. happy path — supplied packaging exists -> set
  2. null clear — packaging_id=None unsets a previous selection
  3. unknown-box reject — packaging not found -> 400

The cross-shop reject case (PKG-1) was removed in PKG-1b when
PackagingBox.shop_id was dropped (shared inventory model).

ORD-BULK-1 — POST /api/orders/bulk-status result classification (bottom half).
"""
import inspect
import pytest
from contextlib import asynccontextmanager
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from routers.orders import bulk_transition_order_status
from services.order_service import update_order
from schemas.order import BulkStatusChangeRequest, OrderUpdate
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


# ─── ORD-BULK-1 — bulk status change ───────────────────────


def _bulk_db(orders_by_id):
    """AsyncMock session whose .get resolves the given id -> order map.

    begin_nested is a MagicMock (not AsyncMock): on a real AsyncSession it returns
    an AsyncSessionTransaction usable with `async with`, not a coroutine.
    """
    db = AsyncMock()
    db.get.side_effect = lambda _model, order_id: orders_by_id.get(order_id)

    @asynccontextmanager
    async def _savepoint():
        yield

    db.begin_nested = MagicMock(side_effect=_savepoint)
    return db


@pytest.mark.asyncio
async def test_bulk_status_updates_every_order_and_commits_once():
    orders = {}
    for _ in range(3):
        order = _make_order(uuid4())
        orders[order.id] = order
    db = _bulk_db(orders)
    user = _make_user(UserRole.OWNER)

    body = BulkStatusChangeRequest(
        order_ids=list(orders.keys()), new_status=OrderStatus.IN_PRODUCTION
    )
    with patch(
        "routers.orders.change_order_status", new_callable=AsyncMock
    ) as change:
        change.side_effect = lambda db, order, status, user, comment: (order, [])
        result = await bulk_transition_order_status(body, user, db)

    assert result.updated == 3
    assert result.unchanged == 0
    assert result.skipped == []
    assert change.await_count == 3
    # Best-effort batch: one commit closes the whole loop.
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_status_counts_order_already_at_target_as_unchanged():
    moving = _make_order(uuid4())
    already = _make_order(uuid4())
    already.status = OrderStatus.IN_PRODUCTION
    orders = {moving.id: moving, already.id: already}
    db = _bulk_db(orders)
    user = _make_user(UserRole.OWNER)

    body = BulkStatusChangeRequest(
        order_ids=[moving.id, already.id], new_status=OrderStatus.IN_PRODUCTION
    )
    with patch(
        "routers.orders.change_order_status", new_callable=AsyncMock
    ) as change:
        change.side_effect = lambda db, order, status, user, comment: (order, [])
        result = await bulk_transition_order_status(body, user, db)

    assert result.updated == 1
    assert result.unchanged == 1
    assert result.skipped == []
    # The no-op order never reaches the service.
    assert change.await_count == 1


@pytest.mark.asyncio
async def test_bulk_status_skips_cancelled_order_for_manager_and_updates_rest():
    ok = _make_order(uuid4())
    cancelled = _make_order(uuid4())
    cancelled.status = OrderStatus.CANCELLED
    orders = {ok.id: ok, cancelled.id: cancelled}
    db = _bulk_db(orders)
    user = _make_user(UserRole.MANAGER)

    def _change(db, order, status, user, comment):
        # Mirrors order_service.py:143-147 for a MANAGER reopening a cancelled order.
        if order.status == OrderStatus.CANCELLED:
            raise HTTPException(
                status_code=403, detail="Only owner can reopen cancelled orders"
            )
        return order, []

    body = BulkStatusChangeRequest(
        order_ids=[ok.id, cancelled.id], new_status=OrderStatus.IN_PRODUCTION
    )
    # USER-ACCESS-1: bulk resolves the caller's shop scope once; give the manager
    # an unrestricted scope so this test stays focused on the cancelled-skip logic.
    from services.access_service import ShopScope
    with patch(
        "routers.orders.get_shop_scope",
        new=AsyncMock(return_value=ShopScope.unrestricted()),
    ):
        with patch(
            "routers.orders.change_order_status", new_callable=AsyncMock
        ) as change:
            change.side_effect = _change
            result = await bulk_transition_order_status(body, user, db)

    assert result.updated == 1
    assert result.unchanged == 0
    assert len(result.skipped) == 1
    assert result.skipped[0].order_id == cancelled.id
    assert result.skipped[0].reason == "Only owner can reopen cancelled orders"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_status_reports_unknown_id_as_not_found():
    missing_id = uuid4()
    db = _bulk_db({})
    user = _make_user(UserRole.OWNER)

    body = BulkStatusChangeRequest(
        order_ids=[missing_id], new_status=OrderStatus.SHIPPED
    )
    with patch("routers.orders.change_order_status", new_callable=AsyncMock):
        result = await bulk_transition_order_status(body, user, db)

    assert result.updated == 0
    assert result.skipped[0].order_id == missing_id
    assert result.skipped[0].reason == "not found"


@pytest.mark.asyncio
async def test_bulk_status_aggregates_warnings_across_batch():
    first = _make_order(uuid4())
    second = _make_order(uuid4())
    orders = {first.id: first, second.id: second}
    db = _bulk_db(orders)
    user = _make_user(UserRole.OWNER)

    def _change(db, order, status, user, comment):
        return order, [f"⚠ Negative stock for {order.id}"]

    body = BulkStatusChangeRequest(
        order_ids=[first.id, second.id], new_status=OrderStatus.SHIPPED
    )
    with patch(
        "routers.orders.change_order_status", new_callable=AsyncMock
    ) as change:
        change.side_effect = _change
        result = await bulk_transition_order_status(body, user, db)

    assert result.updated == 2
    assert len(result.warnings) == 2


def test_bulk_status_route_is_role_gated_to_owner_and_manager():
    param = inspect.signature(bulk_transition_order_status).parameters["current_user"]
    # require_role's inner checker — the OWNER/MANAGER gate (dependencies.py:42).
    assert param.default.dependency.__name__ == "role_checker"
