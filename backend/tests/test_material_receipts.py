"""MAT-2 — Material receipts, ledger, adjustments regression-guards.

Captures the in-memory mutations and `db.add(...)` calls during the receipt /
adjust / overhead-receipt flows. Mirrors the mock-DB pattern in
test_stock_service.py (PKG-2) and test_materials_router.py (MAT-1).

Four required regressions (per task.md §scope):
  1. Receipt path stages a MaterialMovement with reason='receipt' AND links
     it to the created MaterialReceipt by receipt_id.
  2. Receipt path mutates Material.current_unit_cost and Material.stock_quantity
     (weighted-average + stock += qty).
  3. Adjust path stages a MaterialMovement carrying the operator-chosen reason
     and the signed delta.
  4. Overhead receipt path persists shop_id verbatim onto the staged row.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.material import (
    Material,
    MaterialMovement,
    MaterialMovementReason,
    MaterialReceipt,
    OverheadMaterial,
    OverheadMaterialReceipt,
)
from models.user import UserRole
from routers.materials import (
    adjust_material_stock,
    create_material_receipt,
)
from routers.overhead_materials import create_overhead_receipt
from schemas.material import (
    MaterialReceiptCreate,
    MaterialStockAdjustment,
    OverheadMaterialReceiptCreate,
)


def _make_user(role=UserRole.OWNER):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


def _make_material(
    *,
    stock_quantity: Decimal = Decimal("0"),
    current_unit_cost: Decimal = Decimal("0"),
    currency: str = "UAH",
) -> Material:
    """Real Material instance (not MagicMock) so the receipt service can mutate
    its `current_unit_cost` and `stock_quantity` attributes directly."""
    material = Material(
        name="Шкіра італійська чорна",
        unit="dm2",
        currency=currency,
        current_unit_cost=current_unit_cost,
        stock_quantity=stock_quantity,
        low_stock_threshold=Decimal("0"),
        waste_percent=Decimal("0"),
        supplier_name=None,
        notes=None,
        is_active=True,
        # WH-1: column defaults land at INSERT, and this Material is never flushed,
        # so MaterialRead.model_validate would see None on both.
        category="MATERIAL",
        is_stock_tracked=True,
    )
    material.id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    material.created_at = now
    material.updated_at = now
    return material


def _simulate_server_defaults(adds: list) -> None:
    """Stand in for what Postgres assigns at flush/commit (id PK, timestamps).
    Tests use mocked AsyncSession, so without this the Pydantic response
    serializer would see None for not-yet-assigned columns."""
    now = datetime.now(timezone.utc)
    for obj in adds:
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        if hasattr(obj, "received_at") and getattr(obj, "received_at", None) is None:
            obj.received_at = now


def _make_db_for_receipt(material: Material):
    """AsyncSession mock that returns the given material on db.get(Material, ...)
    and captures every db.add() call. Used by the receipt + adjust paths.
    """
    captured_adds: list = []

    async def fake_get(model_cls, ident):
        if model_cls is Material and ident == material.id:
            return material
        return None

    db = MagicMock()
    db.get = AsyncMock(side_effect=fake_get)
    db.add = MagicMock(side_effect=lambda obj: captured_adds.append(obj))

    async def fake_flush(*args, **kwargs):
        _simulate_server_defaults(captured_adds)

    db.flush = AsyncMock(side_effect=fake_flush)
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    return db, captured_adds


@pytest.mark.asyncio
async def test_create_receipt_inserts_movement_with_receipt_id():
    """Receipt POST stages both a MaterialReceipt and a MaterialMovement
    (reason=RECEIPT) — the movement carries receipt_id pointing at the receipt."""
    material = _make_material(
        stock_quantity=Decimal("0"), current_unit_cost=Decimal("0")
    )
    db, adds = _make_db_for_receipt(material)
    user = _make_user()

    body = MaterialReceiptCreate(
        qty=Decimal("25"),
        unit_cost=Decimal("580"),
        currency="UAH",
        shipping_cost=Decimal("200"),
        supplier="Conceria Walpier",
        invoice_no="INV-2026-001",
    )

    await create_material_receipt(
        material_id=material.id, body=body, db=db, user=user
    )

    receipts = [o for o in adds if isinstance(o, MaterialReceipt)]
    movements = [o for o in adds if isinstance(o, MaterialMovement)]
    assert len(receipts) == 1, f"expected 1 MaterialReceipt add, got {len(receipts)}"
    assert len(movements) == 1, f"expected 1 MaterialMovement add, got {len(movements)}"
    assert movements[0].reason == MaterialMovementReason.RECEIPT
    assert movements[0].receipt_id == receipts[0].id
    assert movements[0].delta == Decimal("25")
    assert movements[0].unit_cost_at_movement is None


@pytest.mark.asyncio
async def test_create_receipt_updates_material_weighted_average():
    """Receipt POST mutates Material.current_unit_cost (weighted-average) and
    Material.stock_quantity (+= qty). Verifies both columns are touched in the
    same flow — column-presence guard against accidental drops."""
    material = _make_material(
        stock_quantity=Decimal("0"), current_unit_cost=Decimal("0")
    )
    db, adds = _make_db_for_receipt(material)
    user = _make_user()

    body = MaterialReceiptCreate(
        qty=Decimal("25"),
        unit_cost=Decimal("580"),
        currency="UAH",
        shipping_cost=Decimal("200"),
    )
    await create_material_receipt(
        material_id=material.id, body=body, db=db, user=user
    )

    # Effective unit cost = (25*580 + 200) / 25 = 14700/25 = 588.
    # With prior stock=0, weighted-avg lands at 588.
    assert material.current_unit_cost == Decimal("588")
    assert material.stock_quantity == Decimal("25")


@pytest.mark.asyncio
async def test_create_receipt_rebaselines_cost_when_restocking_negative_to_zero():
    """B-3: negative stock is a permitted state (MAT-4). Restocking a material back
    to exactly zero used to divide by (stock + qty) == 0 → ZeroDivisionError → 500.
    The receipt must now succeed and re-baseline current_unit_cost to the receipt's
    effective unit cost (weighted average is undefined for non-positive stock)."""
    material = _make_material(
        stock_quantity=Decimal("-5"), current_unit_cost=Decimal("100")
    )
    db, adds = _make_db_for_receipt(material)
    user = _make_user()

    body = MaterialReceiptCreate(
        qty=Decimal("5"),
        unit_cost=Decimal("580"),
        currency="UAH",
        shipping_cost=Decimal("200"),
    )
    # Must not raise ZeroDivisionError.
    await create_material_receipt(
        material_id=material.id, body=body, db=db, user=user
    )

    # Effective unit cost = (5*580 + 200) / 5 = 3100/5 = 620. Re-baselined, not blended
    # with the stale current_unit_cost. Stock returns to 0 (-5 + 5).
    assert material.current_unit_cost == Decimal("620")
    assert material.stock_quantity == Decimal("0")


@pytest.mark.asyncio
async def test_adjust_endpoint_writes_adjustment_movement():
    """POST /adjust with reason='waste' and a negative delta stages exactly one
    MaterialMovement with reason=WASTE, the signed delta, and a NULL cost
    snapshot (CHECK constraint compliance)."""
    material = _make_material(
        stock_quantity=Decimal("35"), current_unit_cost=Decimal("597")
    )
    db, adds = _make_db_for_receipt(material)
    user = _make_user()

    body = MaterialStockAdjustment(
        delta=Decimal("-2"),
        reason="waste",
        notes="Cut error",
    )
    await adjust_material_stock(
        material_id=material.id, body=body, db=db, user=user
    )

    movements = [o for o in adds if isinstance(o, MaterialMovement)]
    assert len(movements) == 1
    m = movements[0]
    assert m.reason == MaterialMovementReason.WASTE
    assert m.delta == Decimal("-2")
    assert m.unit_cost_at_movement is None
    assert m.notes == "Cut error"
    # Stock counter decremented accordingly.
    assert material.stock_quantity == Decimal("33")


@pytest.mark.asyncio
async def test_overhead_receipt_persists_shop_id():
    """POST overhead receipt with shop_id resolves the shop (active), then
    stages the OverheadMaterialReceipt with that shop_id carried through."""
    overhead = OverheadMaterial(name="Клей PVA", unit="ml")
    overhead.id = uuid.uuid4()

    shop = MagicMock()
    shop.id = uuid.uuid4()
    shop.name = "KoraKlenu"
    shop.is_active = True

    captured_adds: list = []

    async def fake_get(model_cls, ident):
        if ident == overhead.id:
            return overhead
        if ident == shop.id:
            return shop
        return None

    db = MagicMock()
    db.get = AsyncMock(side_effect=fake_get)
    db.add = MagicMock(side_effect=lambda obj: captured_adds.append(obj))

    async def fake_flush(*args, **kwargs):
        _simulate_server_defaults(captured_adds)

    db.flush = AsyncMock(side_effect=fake_flush)
    db.refresh = AsyncMock()
    db.commit = AsyncMock()

    user = _make_user()
    body = OverheadMaterialReceiptCreate(
        qty=Decimal("3"),
        total_cost=Decimal("450"),
        currency="UAH",
        shop_id=shop.id,
        supplier="ATB",
        invoice_no="OH-001",
    )

    result = await create_overhead_receipt(
        overhead_id=overhead.id, body=body, db=db, user=user
    )

    staged = [o for o in captured_adds if isinstance(o, OverheadMaterialReceipt)]
    assert len(staged) == 1
    assert staged[0].shop_id == shop.id
    assert staged[0].total_cost == Decimal("450")
    assert staged[0].overhead_material_id == overhead.id
    # Response carries the joined shop name for UI display.
    assert result.shop_id == shop.id
    assert result.shop_name == "KoraKlenu"
