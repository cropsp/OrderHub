"""MAT-4 / FX-CONVERSION — order consumption service regression guards.

Validates services.order_consumption_service.consume_materials_for_order via
mocked AsyncSession + MagicMock objects. No real DB. Mirrors the pattern in
test_material_receipts.py (MAT-2) and test_stock_service.py (PKG-2).

Guards:
  1. Idempotency — existing consumption row → no-op, no apply_movement calls.
  2. Happy path — single BOM-equipped item produces the expected cost SUM.
  3. waste_percent shows up in the per-line delta passed to apply_movement.
  4. FX — a UAH-priced recipe books a converted cost onto a USD order, with the
     rate + basis recorded; an unconvertible currency (or no rate at all)
     degrades to cost=None + warning while apply_movement STILL fires, so
     inventory stays honest.
  5. Partial BOM coverage — bool flag + warning + cost reflects only BOM items.
  6. Negative stock — material name surfaced AND consumption movement still
     staged (permissive race policy).
  7. WH-1 is_stock_tracked=false — the line prices in exactly as a tracked one
     would, but stages no movement, moves no counter and raises no negative-stock
     warning; an unset flag still consumes; the FX check stays outside the branch.
  8. WH-1 second idempotency probe — an already-booked computed_production_cost
     blocks a re-ship from re-pricing a frozen snapshot when no ledger row exists
     to block it (all-untracked recipes).

The mock session dispatches on the ENTITY BEING QUERIED, not on call order. It
used to key off a call counter with the comment "we rely on call order matching
the iteration order of items" — which meant any new query inside the service
silently shifted every subsequent result, and because these are MagicMocks the
mis-wiring failed OPEN rather than raising. An unrecognised query now raises.
"""

import re
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.bom import BomItem
from models.material import Material, MaterialMovement, MaterialMovementReason
from models.order import OrderItem
from services.fx_service import FxRates
from services.order_consumption_service import (
    ConsumptionResult,
    consume_materials_for_order,
)

# UAH per 1 USD, NBU quote direction. UAH costs DIVIDE by this.
RATE = Decimal("41.5")


def _fx(rate: Decimal | None = RATE) -> FxRates:
    if rate is None:
        return FxRates.unavailable()
    return FxRates(uah_per_usd=rate, source="manual")


def _make_material(
    *,
    name: str = "Шкіра італійська чорна",
    currency: str = "UAH",
    unit_cost: Decimal = Decimal("580"),
    stock: Decimal = Decimal("100"),
    waste: Decimal = Decimal("0"),
    is_stock_tracked: bool | None = True,
) -> Material:
    """Real Material instance so apply_movement can mutate stock_quantity.

    `is_stock_tracked` is set explicitly (column defaults apply at INSERT, and this
    object is never flushed) and accepts None so a test can assert the WH-1 rule
    that an unset flag means TRACKED.
    """
    material = Material(
        name=name,
        unit="dm2",
        currency=currency,
        current_unit_cost=unit_cost,
        stock_quantity=stock,
        low_stock_threshold=Decimal("0"),
        waste_percent=waste,
        is_active=True,
        category="MATERIAL",
        is_stock_tracked=is_stock_tracked,
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


def _queried_entity(stmt):
    """The ORM entity a select() targets, e.g. MaterialMovement for
    select(MaterialMovement.id)."""
    descriptions = stmt.column_descriptions
    return descriptions[0]["entity"] if descriptions else None


def _bound_uuid(stmt):
    """The single UUID bind in the BOM query's WHERE clause (product_id)."""
    for value in stmt.compile().params.values():
        if isinstance(value, uuid.UUID):
            return value
    return None


def _make_db(*, idempotent_hit: bool, items: list, bom_lookup: dict):
    """Mock AsyncSession, dispatching on the queried entity.

    - select(MaterialMovement.id) — idempotency probe; .scalar() yields a UUID
      when `idempotent_hit` is True, else None.
    - select(OrderItem)          — items query.
    - select(BomItem)            — BOM rows for the product_id in the WHERE
                                   clause, looked up in `bom_lookup`.
    - db.get(Material, ...)      — the Material row apply_movement loads.

    Anything else raises. Dispatching on identity rather than call order is what
    keeps this harness honest when the service gains or loses a query.
    """
    captured_adds: list = []
    materials_by_id = {}
    for boms in bom_lookup.values():
        for bom in boms:
            materials_by_id[bom.material.id] = bom.material

    def make_result(scalar_value=None, scalars_iter=None):
        result = MagicMock()
        result.scalar = MagicMock(return_value=scalar_value)
        if scalars_iter is not None:
            scalars_mock = MagicMock()
            scalars_mock.__iter__ = lambda self: iter(scalars_iter)
            result.scalars = MagicMock(return_value=scalars_mock)
        return result

    async def fake_execute(stmt):
        entity = _queried_entity(stmt)
        if entity is MaterialMovement:
            return make_result(
                scalar_value=(uuid.uuid4() if idempotent_hit else None)
            )
        if entity is OrderItem:
            return make_result(scalars_iter=items)
        if entity is BomItem:
            return make_result(scalars_iter=bom_lookup.get(_bound_uuid(stmt), []))
        raise AssertionError(
            f"Unexpected query against {entity!r} in consume_materials_for_order. "
            f"If the service gained a query, teach this harness about it — do not "
            f"let it fall through to a MagicMock."
        )

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


def _make_order(currency: str = "UAH", computed_production_cost=None):
    order = MagicMock()
    order.id = uuid.uuid4()
    order.currency = currency
    # WH-1: the idempotency guard also reads this. It MUST be set explicitly — a
    # bare MagicMock attribute is truthy, which would silently turn every test in
    # this module into an idempotent skip.
    order.computed_production_cost = computed_production_cost
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
# 4. FX conversion (FX-CONVERSION)
# ---------------------------------------------------------------------------

def _uah_recipe_on_usd_order(*, unit_cost=Decimal("100"), qty_per_unit=Decimal("5.00")):
    material = _make_material(currency="UAH", unit_cost=unit_cost, stock=Decimal("50"))
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=qty_per_unit)
    item = _make_item(variant=_make_variant(product_id), quantity=1)
    db, _ = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )
    return material, db


@pytest.mark.asyncio
async def test_uah_materials_book_a_converted_cost_on_a_usd_order():
    """The whole point of the sprint: UAH warehouse cost reaching a USD order.

    5.00 dm2 x 1 x 100 UAH = 500 UAH; 500 / 41.5 = 12.0481... -> 12.05 USD.
    """
    material, db = _uah_recipe_on_usd_order()

    result = await consume_materials_for_order(
        db, _make_order(currency="USD"), uuid.uuid4(), fx=_fx()
    )

    assert result.computed_production_cost == Decimal("12.05")
    assert result.warnings == []
    assert material.stock_quantity == Decimal("45.00")


@pytest.mark.asyncio
async def test_conversion_is_division_not_multiplication():
    """Direction guard at the booking layer (see also test_fx_direction.py).
    500 * 41.5 = 20750 — a number that would sail through every downstream sum."""
    _material, db = _uah_recipe_on_usd_order()

    result = await consume_materials_for_order(
        db, _make_order(currency="USD"), uuid.uuid4(), fx=_fx()
    )

    assert result.computed_production_cost < Decimal("500")
    assert result.computed_production_cost != Decimal("20750.00")


@pytest.mark.asyncio
async def test_the_rate_and_basis_are_recorded_for_audit():
    """Forward-only means a booking that cannot be explained cannot be repaired."""
    _material, db = _uah_recipe_on_usd_order()

    result = await consume_materials_for_order(
        db, _make_order(currency="USD"), uuid.uuid4(), fx=_fx()
    )

    assert result.fx_rate_used == RATE
    assert result.basis_currency == "UAH"
    assert result.basis_amount == Decimal("500.0000")
    # The stored triple reconstructs the booked figure.
    reconstructed = result.basis_amount / result.fx_rate_used
    assert reconstructed.quantize(Decimal("0.01")) == result.computed_production_cost


@pytest.mark.asyncio
async def test_same_currency_books_directly_and_stamps_no_rate():
    """KoraKlenu is unchanged by this sprint: UAH materials, UAH order, no FX."""
    material = _make_material(currency="UAH", unit_cost=Decimal("100"))
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=Decimal("5.00"))
    item = _make_item(variant=_make_variant(product_id), quantity=1)
    db, _ = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )

    result = await consume_materials_for_order(
        db, _make_order(currency="UAH"), uuid.uuid4(), fx=_fx()
    )

    assert result.computed_production_cost == Decimal("500.00")
    # NULL rate + non-NULL cost is the documented "no conversion applied" state.
    assert result.fx_rate_used is None


@pytest.mark.asyncio
async def test_no_rate_configured_degrades_but_still_consumes():
    """Task rule 4 — a missing rate must never hard-fail the SHIPPED transition."""
    material, db = _uah_recipe_on_usd_order()

    result = await consume_materials_for_order(
        db, _make_order(currency="USD"), uuid.uuid4(), fx=_fx(None)
    )

    assert result.computed_production_cost is None
    assert result.fx_rate_used is None
    assert any("no exchange rate" in w for w in result.warnings)
    # CONSUMPTION STILL FIRED — stock honest.
    assert material.stock_quantity == Decimal("45.00")


@pytest.mark.asyncio
async def test_an_unsupported_order_currency_degrades_rather_than_using_the_usd_rate():
    """Task rule 1: only UAH<->USD is built. A EUR order must NOT be converted at
    the USD rate — that would be wrong by the EUR/USD cross, silently."""
    material, db = _uah_recipe_on_usd_order()

    result = await consume_materials_for_order(
        db, _make_order(currency="EUR"), uuid.uuid4(), fx=_fx()
    )

    assert result.computed_production_cost is None
    assert material.stock_quantity == Decimal("45.00")


@pytest.mark.asyncio
async def test_one_unconvertible_bucket_nulls_the_whole_cost():
    """All-or-nothing. Booking only the convertible bucket would under-state COGS
    and over-state profit — a plausible wrong number, which is worse than none."""
    uah = _make_material(name="Шкіра", currency="UAH", unit_cost=Decimal("100"))
    gbp = _make_material(name="Нитка", currency="GBP", unit_cost=Decimal("10"))
    product_id = uuid.uuid4()
    boms = [
        _make_bom_item(material=uah, qty_per_unit=Decimal("5.00")),
        _make_bom_item(material=gbp, qty_per_unit=Decimal("1.00")),
    ]
    item = _make_item(variant=_make_variant(product_id), quantity=1)
    db, _ = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: boms}
    )

    result = await consume_materials_for_order(
        db, _make_order(currency="USD"), uuid.uuid4(), fx=_fx()
    )

    assert result.computed_production_cost is None
    # Both materials still consumed.
    assert uah.stock_quantity == Decimal("95.00")
    assert gbp.stock_quantity == Decimal("99.00")


@pytest.mark.asyncio
async def test_mixed_convertible_currencies_book_but_record_no_single_basis():
    """UAH + USD materials on a USD order: everything converts, so a cost is
    booked — but no single basis figure can describe it, so basis stays NULL."""
    uah = _make_material(name="Шкіра", currency="UAH", unit_cost=Decimal("100"))
    usd = _make_material(name="Zip", currency="USD", unit_cost=Decimal("2"))
    product_id = uuid.uuid4()
    boms = [
        _make_bom_item(material=uah, qty_per_unit=Decimal("5.00")),  # 500 UAH
        _make_bom_item(material=usd, qty_per_unit=Decimal("1.00")),  # 2 USD
    ]
    item = _make_item(variant=_make_variant(product_id), quantity=1)
    db, _ = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: boms}
    )

    result = await consume_materials_for_order(
        db, _make_order(currency="USD"), uuid.uuid4(), fx=_fx()
    )

    # 500/41.5 + 2 = 12.0481... + 2 = 14.0481... -> 14.05
    assert result.computed_production_cost == Decimal("14.05")
    assert result.fx_rate_used == RATE
    assert result.basis_amount is None
    assert result.basis_currency is None


@pytest.mark.asyncio
async def test_currency_codes_are_normalised_before_the_fx_lookup():
    """Material.currency is a bare String(3) with no CHECK — a stray lowercase
    value must not read as an unknown currency and silently null the cost."""
    material = _make_material(currency=" uah ", unit_cost=Decimal("100"))
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=Decimal("5.00"))
    item = _make_item(variant=_make_variant(product_id), quantity=1)
    db, _ = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )

    result = await consume_materials_for_order(
        db, _make_order(currency="usd"), uuid.uuid4(), fx=_fx()
    )

    assert result.computed_production_cost == Decimal("12.05")
    assert result.basis_currency == "UAH"


@pytest.mark.asyncio
async def test_rounding_happens_once_at_the_end_not_per_bucket():
    """A repeating decimal pins the quantize-once rule. Rounding each bucket first
    would drift from bom_service's preview, which folds identically."""
    material = _make_material(currency="UAH", unit_cost=Decimal("100"))
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=Decimal("1.00"))
    item = _make_item(variant=_make_variant(product_id), quantity=1)
    db, _ = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )

    # 100 UAH / 3 = 33.3333... -> 33.33
    result = await consume_materials_for_order(
        db, _make_order(currency="USD"), uuid.uuid4(), fx=_fx(Decimal("3"))
    )

    assert result.computed_production_cost == Decimal("33.33")


@pytest.mark.asyncio
async def test_fx_warnings_never_contain_amounts_or_rates():
    """routers/shipping.py returns these warnings in a raw dict with no
    response_model, so they bypass censor_order_financials AND the money-field
    guard entirely. They must therefore carry no money at all."""
    _material, db = _uah_recipe_on_usd_order()

    result = await consume_materials_for_order(
        db, _make_order(currency="USD"), uuid.uuid4(), fx=_fx(None)
    )

    assert result.warnings
    for warning in result.warnings:
        assert not re.search(r"\d+[.,]\d", warning), f"money leaked into: {warning!r}"


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


# ---------------------------------------------------------------------------
# 7. WH-1 — is_stock_tracked=false: cost yes, stock no
# ---------------------------------------------------------------------------

def _movements(adds: list) -> list:
    return [o for o in adds if isinstance(o, MaterialMovement)]


@pytest.mark.asyncio
async def test_untracked_material_prices_in_but_stages_no_movement():
    """An untracked line books exactly the cost a tracked one would, and touches
    neither the ledger nor the counter. This is SVC-MATERIAL-NONSTOCK: services
    (cutting, sewing) are modelled as materials and used to bleed stock forever."""
    material = _make_material(
        name="Лазерна порізка",
        unit_cost=Decimal("100"),
        stock=Decimal("50"),
        is_stock_tracked=False,
    )
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=Decimal("5.00"))
    item = _make_item(variant=_make_variant(product_id), quantity=2)

    order = _make_order(currency="UAH")
    db, adds = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )

    result = await consume_materials_for_order(db, order, uuid.uuid4())

    # Same 5.00 × 2 × 100 = 1000.00 as the tracked happy path above.
    assert result.computed_production_cost == Decimal("1000.00")
    assert material.stock_quantity == Decimal("50"), "stock must not move"
    assert _movements(adds) == [], "no ledger row for an untracked line"
    assert result.warnings == []


@pytest.mark.asyncio
async def test_untracked_material_at_zero_stock_raises_no_negative_warning():
    """The whole point: an untracked material sits at 0 forever and must never
    produce the 'went negative' nag it produces today."""
    material = _make_material(
        name="Пошиття",
        unit_cost=Decimal("40"),
        stock=Decimal("0"),
        is_stock_tracked=False,
    )
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=Decimal("3.00"))
    item = _make_item(variant=_make_variant(product_id), quantity=1)

    order = _make_order(currency="UAH")
    db, adds = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )

    result = await consume_materials_for_order(db, order, uuid.uuid4())

    assert result.negative_stock_materials == []
    assert result.warnings == []
    assert material.stock_quantity == Decimal("0")
    assert _movements(adds) == []
    assert result.computed_production_cost == Decimal("120.00")


@pytest.mark.asyncio
async def test_mixed_tracked_and_untracked_lines_in_one_recipe():
    """The realistic recipe: leather (tracked) + laser cutting (untracked).
    One movement, one decrement, both costs."""
    leather = _make_material(
        name="Шкіра", unit_cost=Decimal("500"), stock=Decimal("10")
    )
    service = _make_material(
        name="Лазерна порізка",
        unit_cost=Decimal("25"),
        stock=Decimal("0"),
        is_stock_tracked=False,
    )
    product_id = uuid.uuid4()
    boms = [
        _make_bom_item(material=leather, qty_per_unit=Decimal("2.00")),
        _make_bom_item(material=service, qty_per_unit=Decimal("1.00")),
    ]
    item = _make_item(variant=_make_variant(product_id), quantity=1)

    order = _make_order(currency="UAH")
    db, adds = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: boms}
    )

    result = await consume_materials_for_order(db, order, uuid.uuid4())

    # 2 × 500 + 1 × 25 = 1025.00 — both lines priced.
    assert result.computed_production_cost == Decimal("1025.00")
    assert leather.stock_quantity == Decimal("8.00")
    assert service.stock_quantity == Decimal("0")
    movements = _movements(adds)
    assert len(movements) == 1
    assert movements[0].material_id == leather.id


@pytest.mark.asyncio
async def test_material_with_unset_flag_is_treated_as_tracked():
    """Skipping stock is an explicit opt-in. A Material whose flag was never set
    (transient object, column defaults land at INSERT) must still consume —
    the alternative is silent, permanent stock loss."""
    material = _make_material(
        unit_cost=Decimal("100"), stock=Decimal("50"), is_stock_tracked=None
    )
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=Decimal("5.00"))
    item = _make_item(variant=_make_variant(product_id), quantity=1)

    order = _make_order(currency="UAH")
    db, adds = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )

    await consume_materials_for_order(db, order, uuid.uuid4())

    assert material.stock_quantity == Decimal("45.00")
    assert len(_movements(adds)) == 1


@pytest.mark.asyncio
async def test_untracked_line_in_an_unconvertible_currency_still_nulls_the_cost():
    """The FX check sits OUTSIDE the tracking branch. An untracked line priced in
    a currency with no rate must still void the whole rollup — booking only the
    convertible part would under-state COGS exactly as it would for a tracked one."""
    service = _make_material(
        name="Cutting service",
        currency="EUR",
        unit_cost=Decimal("10"),
        stock=Decimal("0"),
        is_stock_tracked=False,
    )
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=service, qty_per_unit=Decimal("1.00"))
    item = _make_item(variant=_make_variant(product_id), quantity=1)

    order = _make_order(currency="USD")
    db, adds = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )

    result = await consume_materials_for_order(db, order, uuid.uuid4(), fx=_fx())

    assert result.computed_production_cost is None
    assert any("no exchange rate" in w for w in result.warnings)
    assert _movements(adds) == []


# ---------------------------------------------------------------------------
# 8. WH-1 — the second idempotency probe (a booked cost is a frozen snapshot)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reship_of_an_untracked_only_order_does_not_reprice_it():
    """An all-untracked recipe leaves NO ledger row, so the movement probe alone
    would let SHIPPED → IN_PROGRESS → SHIPPED recompute a frozen snapshot at
    today's WAC and today's rate. The already-booked cost is the second probe."""
    material = _make_material(
        unit_cost=Decimal("999"), stock=Decimal("0"), is_stock_tracked=False
    )
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=Decimal("1.00"))
    item = _make_item(variant=_make_variant(product_id), quantity=1)

    order = _make_order(currency="UAH", computed_production_cost=Decimal("500.00"))
    db, adds = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )

    result = await consume_materials_for_order(db, order, uuid.uuid4())

    assert result.idempotent_skip is True
    assert result.computed_production_cost is None, (
        "the caller must not overwrite the frozen snapshot on a skip"
    )
    assert _movements(adds) == []


@pytest.mark.asyncio
async def test_reship_after_an_fx_failure_still_recomputes():
    """The accepted delta of that second probe: cost=None and no movements means
    nothing was ever booked, so a later ship (once a rate exists) is a recovery,
    not a re-price."""
    material = _make_material(
        unit_cost=Decimal("100"), stock=Decimal("0"), is_stock_tracked=False
    )
    product_id = uuid.uuid4()
    bom = _make_bom_item(material=material, qty_per_unit=Decimal("2.00"))
    item = _make_item(variant=_make_variant(product_id), quantity=1)

    order = _make_order(currency="UAH", computed_production_cost=None)
    db, _adds = _make_db(
        idempotent_hit=False, items=[item], bom_lookup={product_id: [bom]}
    )

    result = await consume_materials_for_order(db, order, uuid.uuid4())

    assert result.idempotent_skip is False
    assert result.computed_production_cost == Decimal("200.00")
