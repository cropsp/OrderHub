"""PKG-2 — Unit tests for services.stock_service.apply_movement.

Verifies the contract:
- One ledger row is staged (db.add) per call.
- box.stock_quantity is mutated in-Python (no internal commit).
- A warning is returned when the post-delta counter goes negative.
- A missing box raises HTTPException(404) and stages nothing.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from models.stock_movement import PackagingStockMovement, StockMovementReason
from services import stock_service


def _make_box(stock_quantity: int = 0, name: str = "Box M"):
    box = MagicMock()
    box.id = uuid.uuid4()
    box.name = name
    box.stock_quantity = stock_quantity
    return box


def _make_db(box):
    """db.get(PackagingBox, box_id) -> box; db.add records the ledger row."""
    db = MagicMock()
    db.get = AsyncMock(return_value=box)
    db.add = MagicMock()
    return db


@pytest.mark.asyncio
async def test_apply_movement_initial_stock_increments_counter_and_stages_row():
    box = _make_box(stock_quantity=0)
    db = _make_db(box)
    user_id = uuid.uuid4()

    warnings = await stock_service.apply_movement(
        db,
        box_id=box.id,
        delta=+10,
        reason=StockMovementReason.INITIAL_STOCK,
        user_id=user_id,
    )

    assert warnings == []
    assert box.stock_quantity == 10
    db.add.assert_called_once()
    movement = db.add.call_args.args[0]
    assert isinstance(movement, PackagingStockMovement)
    assert movement.delta == 10
    assert movement.reason == StockMovementReason.INITIAL_STOCK
    assert movement.box_id == box.id
    assert movement.user_id == user_id
    assert movement.order_id is None


@pytest.mark.asyncio
async def test_apply_movement_ttn_create_decrements_with_order_id():
    box = _make_box(stock_quantity=10)
    db = _make_db(box)
    order_id = uuid.uuid4()
    user_id = uuid.uuid4()

    warnings = await stock_service.apply_movement(
        db,
        box_id=box.id,
        delta=-1,
        reason=StockMovementReason.TTN_CREATE,
        user_id=user_id,
        order_id=order_id,
    )

    assert warnings == []
    assert box.stock_quantity == 9
    movement = db.add.call_args.args[0]
    assert movement.delta == -1
    assert movement.reason == StockMovementReason.TTN_CREATE
    assert movement.order_id == order_id


@pytest.mark.asyncio
async def test_apply_movement_warns_when_counter_goes_negative():
    box = _make_box(stock_quantity=0, name="100x120x50")
    db = _make_db(box)

    warnings = await stock_service.apply_movement(
        db,
        box_id=box.id,
        delta=-1,
        reason=StockMovementReason.TTN_CREATE,
        user_id=uuid.uuid4(),
        order_id=uuid.uuid4(),
    )

    assert box.stock_quantity == -1
    assert len(warnings) == 1
    assert "100x120x50" in warnings[0]
    assert "-1" in warnings[0]


@pytest.mark.asyncio
async def test_apply_movement_missing_box_raises_404_without_staging():
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    db.add = MagicMock()

    with pytest.raises(HTTPException) as exc:
        await stock_service.apply_movement(
            db,
            box_id=uuid.uuid4(),
            delta=+5,
            reason=StockMovementReason.RESTOCK,
            user_id=uuid.uuid4(),
        )

    assert exc.value.status_code == 404
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_apply_movement_restock_records_note():
    box = _make_box(stock_quantity=2)
    db = _make_db(box)

    await stock_service.apply_movement(
        db,
        box_id=box.id,
        delta=+8,
        reason=StockMovementReason.RESTOCK,
        user_id=uuid.uuid4(),
        note="shelf count after audit",
    )

    movement = db.add.call_args.args[0]
    assert box.stock_quantity == 10
    assert movement.note == "shelf count after audit"
    assert movement.reason == StockMovementReason.RESTOCK


@pytest.mark.asyncio
async def test_apply_movement_does_not_commit():
    """Service must NOT call db.commit — caller controls the txn boundary."""
    box = _make_box(stock_quantity=0)
    db = _make_db(box)
    db.commit = AsyncMock()

    await stock_service.apply_movement(
        db,
        box_id=box.id,
        delta=+1,
        reason=StockMovementReason.ADJUSTMENT,
        user_id=uuid.uuid4(),
    )

    db.commit.assert_not_called()
