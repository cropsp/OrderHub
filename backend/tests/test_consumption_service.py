"""MAT-4 — order consumption service regression guards.

Validates services.order_consumption_service.consume_materials_for_order via
mocked AsyncSession + MagicMock objects. No real DB. Mirrors the pattern in
test_material_receipts.py (MAT-2) and test_stock_service.py (PKG-2).

Six guards (per task.md §scope):
  1. Idempotency — existing consumption row → no-op, no apply_movement calls.
  2. Happy path — single BOM-equipped item produces the expected cost SUM.
  3. waste_percent shows up in the per-line delta passed to apply_movement.
  4. Currency mismatch — cost rollup skipped (None) AND warning surfaced AND
     apply_movement STILL called (inventory stays honest).
  5. Partial BOM coverage — bool flag + warning + cost reflects only BOM items.
  6. Negative stock — material name surfaced AND consumption movement still
     staged (permissive race policy).
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.material import Material, MaterialMovementReason
from services.order_consumption_service import (
    ConsumptionResult,
    consume_materials_for_order,
)


def _make_material(
    *,
    name: str = "Шкіра італійська чорна",
    currency: str = "UAH",
    unit_cost: Decimal = Decimal("580"),
    stock: Decimal = Decimal("100"),
    waste: Decimal = Decimal("0"),
) -> Material:
    """Real Material instance so apply_movement can mutate stock_quantity."""
    material = Material(
        name=name,
        unit="dm2",
        currency=currency,
        current_unit_cost=unit_cost,
        stock_quantity=stock,
        low_stock_threshold=Decimal("0"),
        waste_percent=waste,
        is_active=True,
    )
    material.id = uuid.uuid4()
    return material


def _make_variant(product_id: uuid.UUID | None = None):
    variant = MagicMock()
    variant.product_id = product_id if product_id is not None else uuid.uuid4()
    return variant


def _make_item(*, variant, quantity: int = 1):
    item = MagicMock()
    item.variant = variant
    item.quantity = quantity
    return item


def _make_bom_item(*, material: Material, qty_per_unit: Decimal):
    bom = MagicMock()
    bom.qty_per_unit = qty_per_unit
    bom.material = material
    bom.material_id = material.id
    return bom


def _make_db(*, idempotent_hit: bool, items: list, bom_lookup: dict):
    """Mock AsyncSession.

    - First db.execute() — idempotency probe; returns a result whose .scalar()
      gives an int when `idempotent_hit` is True, else None.
    - Second db.execute() — items query; returns a result whose .scalars() is
      an iterable of OrderItem MagicMocks.
    - Subsequent db.execute() — BOM query per item; mapped via `bom_lookup`
      keyed by product_id.
    - db.get(Material, ...) returns the Material with that id (used by
      apply_movement to load the material row).
    """
    captured_adds: list = []
    materials_by_id = {}
    for boms in bom_lookup.values():
        for bom in boms:
            materials_by_id[bom.material.id] = bom.material

    call_index = {"n": 0}

    def make_result(scalar_value=None, scalars_iter=None):
        result = MagicMock()
        result.scalar = MagicMock(return_value=scalar_value)
        if scalars_iter is not None:
            scalars_mock = MagicMock()
            scalars_mock.__iter__ = lambda self: iter(scalars_iter)
            result.scalars = MagicMock(return_value=scalars_mock)
        return result

    async def fake_execute(stmt):
        idx = call_index["n"]
        call_index["n"] += 1
        if idx == 0:
            # Idempotency probe.
            return make_result(scalar_value=(uuid.uuid4() if idempotent_hit else None))
        if idx == 1:
            # Items query.
            return make_result(scalars_iter=items)
        # BOM query — derive product_id from the WHERE-clause params is fiddly;
        # we instead rely on call order matching the iteration order of items.
        item_idx = idx - 2
        bom_items_for_call: list = []
        if item_idx < len(items):
            variant = items[item_idx].variant
            if variant is not None and variant.product_id in bom_lookup:
                bom_items_for_call = bom_lookup[variant.product_id]
        return make_result(scalars_iter=bom_items_for_call)

    async def fake_get(model_cls, ident):
        if model_cls is Material:
            return materials_by_id.get(ident)
        return None

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.get = AsyncMock(side_effect=fake_get)
    db.add = MagicMock(side_effect=lambda obj: captured_adds.append(obj))
    db.flush = AsyncMock()
    return db, captured_adds


def _make_order(currency: str = "UAH"):
    order = MagicMock()
    order.id = uuid.uuid4()
    order.currency = currency
    return order


# ---------------------------------------------------------------------------
# 1. Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consume_skips_when_idempotent():
    """Existing consumption ledger row → result.idempotent_skip=True, no work."""
    order = _make_order()
    db, adds = _make_db(idempotent_hit=True, items=[], bom_lookup={})

    result = await consume_materials_for_order(db, order, uuid.uuid4())

    assert isinstance(result, ConsumptionResult)
    assert result.idempotent_skip is True
    assert result.computed_production_cost is None
    assert result.warnings == []
    # No movement stages.
    assert all(getattr(o, "__class__", None).__name__ != "MaterialMovement" for o in adds)
    db.execute.assert_awaited()  # idempotency probe ran


# ---------------------------------------------------------------------------
# 2. Happy path cost computation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consume_computes_cost_for_bom_equipped_items():
    """Single item qty=2; BOM has 1 row (5 dm² × 100 UAH); waste=0 → 1000 UAH."""
    material = _make_material(unit_cost=Decimal("100"), stock=Decimal("50"))
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=Decimal("5.00"))
    item = _make_item(variant=_make_variant(product_id), quantity=2)

    order = _make_order(currency="UAH")
    db, _adds = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )

    result = await consume_materials_for_order(db, order, uuid.uuid4())

    # 5.00 × 2 × (1 + 0/100) × 100 = 1000.00
    assert result.computed_production_cost == Decimal("1000.00")
    assert result.idempotent_skip is False
    assert result.partial_bom_coverage is False
    # Stock decremented by 10.00 (5 × 2).
    assert material.stock_quantity == Decimal("40.00")
    assert result.warnings == []


# ---------------------------------------------------------------------------
# 3. waste_percent applies at consumption time
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consume_applies_waste_percent():
    """waste_percent=10 → delta = qty_per_unit × order_qty × 1.10."""
    material = _make_material(waste=Decimal("10"), stock=Decimal("50"))
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=Decimal("5.00"))
    item = _make_item(variant=_make_variant(product_id), quantity=1)

    order = _make_order(currency="UAH")
    db, _ = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )

    await consume_materials_for_order(db, order, uuid.uuid4())

    # 5.00 × 1 × (1 + 10/100) = 5.50 → stock 50 - 5.50 = 44.50
    assert material.stock_quantity == Decimal("44.50")


# ---------------------------------------------------------------------------
# 4. Currency mismatch — skip cost, KEEP consumption
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consume_skips_cost_on_currency_mismatch():
    """Material in UAH, Order in USD → cost None + warning, but stock decremented."""
    material = _make_material(currency="UAH", stock=Decimal("50"))
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=Decimal("5.00"))
    item = _make_item(variant=_make_variant(product_id), quantity=1)

    order = _make_order(currency="USD")
    db, _ = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )

    result = await consume_materials_for_order(db, order, uuid.uuid4())

    assert result.computed_production_cost is None
    assert any(
        "materials in this order are priced in a different currency" in w
        and "(USD)" in w
        for w in result.warnings
    )
    # CONSUMPTION STILL FIRED — stock honest.
    assert material.stock_quantity == Decimal("45.00")


# ---------------------------------------------------------------------------
# 5. Partial BOM coverage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consume_handles_partial_bom_coverage():
    """2 items; only one product has BOM. Cost reflects BOM item only;
    partial_bom_coverage flag + diagnostic warning surfaced."""
    material = _make_material(unit_cost=Decimal("100"), stock=Decimal("50"))
    product_with_bom = uuid.uuid4()
    product_without_bom = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=Decimal("3.00"))

    item_with = _make_item(variant=_make_variant(product_with_bom), quantity=1)
    item_without = _make_item(variant=_make_variant(product_without_bom), quantity=1)

    order = _make_order(currency="UAH")
    db, _ = _make_db(
        idempotent_hit=False,
        items=[item_with, item_without],
        bom_lookup={product_with_bom: [bom], product_without_bom: []},
    )

    result = await consume_materials_for_order(db, order, uuid.uuid4())

    # 3.00 × 1 × 100 = 300.00 (only the BOM-equipped item contributes)
    assert result.computed_production_cost == Decimal("300.00")
    assert result.partial_bom_coverage is True
    assert any("1 of 2 line items" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 6. Negative stock — permissive race
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consume_surfaces_negative_stock():
    """Stock=1, consumption=2 → goes negative; movement still staged, name
    surfaced in negative_stock_materials + warning."""
    material = _make_material(
        name="Шкіра тестова",
        unit_cost=Decimal("100"),
        stock=Decimal("1"),
    )
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=Decimal("2.00"))
    item = _make_item(variant=_make_variant(product_id), quantity=1)

    order = _make_order(currency="UAH")
    db, _ = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )

    result = await consume_materials_for_order(db, order, uuid.uuid4())

    # Movement applied: stock 1 - 2 = -1 (commits per permissive race policy).
    assert material.stock_quantity == Decimal("-1.00")
    assert "Шкіра тестова" in result.negative_stock_materials
    assert any("went negative" in w for w in result.warnings)
    # Cost still computed — currency matched, BOM present.
    assert result.computed_production_cost == Decimal("200.00")
