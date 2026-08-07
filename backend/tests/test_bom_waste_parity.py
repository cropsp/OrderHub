"""BOM-WASTE-1 — preview-cost == booked-COGS parity guard.

The regression this locks down: `bom_service.compute_bom_cost` (what the
operator reviews) and `order_consumption_service.consume_materials_for_order`
(what a shipment books into `Order.computed_production_cost`) are two separate
implementations of the same number. They silently diverged as soon as a
material's `waste_percent > 0` — the operator signed off on 190.43 UAH while a
shipped unit booked ~201.62.

Rather than assert either side against a hand-computed constant (which lets both
drift together), every test here drives BOTH real services over ONE shared BOM
fixture and asserts they agree to the kopeck. Cost feeds partner payouts, so
"to the kopeck" is the requirement, not a nicety.

Mock AsyncSession throughout — no real DB, matching test_bom_router.py (compiled
SQL / mocked results) and test_consumption_service.py (MagicMock ORM objects).
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.material import Material
from services.bom_service import compute_bom_cost
from services.fx_service import FxRates
from services.order_consumption_service import consume_materials_for_order


# ── Shared fixture: one BOM, two harnesses ─────────────────

class Line:
    """One recipe line, expressed once and fed to both services."""

    def __init__(
        self,
        qty: str,
        unit_cost: str,
        waste: str,
        currency: str = "UAH",
        is_stock_tracked: bool = True,
    ):
        self.qty = Decimal(qty)
        self.unit_cost = Decimal(unit_cost)
        self.waste = Decimal(waste)
        self.currency = currency
        # WH-1: whether the line moves stock is irrelevant to what it costs, and
        # the preview does not even know about it — parity must hold regardless.
        self.is_stock_tracked = is_stock_tracked


def _preview_db(lines: list[Line]):
    """AsyncSession mock for compute_bom_cost — one row per line, in the
    (currency, qty_per_unit, current_unit_cost, waste_percent) shape its SELECT
    projects."""
    rows = [(ln.currency, ln.qty, ln.unit_cost, ln.waste) for ln in lines]

    async def fake_execute(_stmt):
        result = MagicMock()
        result.all.return_value = rows
        return result

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    return db


def _consumption_db(lines: list[Line], product_id: uuid.UUID, quantity: int):
    """AsyncSession mock for consume_materials_for_order.

    Call order (order_consumption_service.py:61-105): idempotency probe →
    OrderItem query → one BOM query per item. Real Material instances so
    apply_movement can mutate stock_quantity.
    """
    materials = [
        Material(
            name=f"material-{i}",
            unit="dm2",
            currency=ln.currency,
            current_unit_cost=ln.unit_cost,
            stock_quantity=Decimal("10000"),
            low_stock_threshold=Decimal("0"),
            waste_percent=ln.waste,
            is_active=True,
            category="MATERIAL",
            is_stock_tracked=ln.is_stock_tracked,
        )
        for i, ln in enumerate(lines)
    ]
    for m in materials:
        m.id = uuid.uuid4()

    bom_items = []
    for material, ln in zip(materials, lines):
        bom = MagicMock()
        bom.qty_per_unit = ln.qty
        bom.material = material
        bom.material_id = material.id
        bom_items.append(bom)

    variant = MagicMock()
    variant.product_id = product_id
    item = MagicMock()
    item.variant = variant
    item.quantity = quantity

    materials_by_id = {m.id: m for m in materials}
    call_index = {"n": 0}

    def make_result(scalar_value=None, scalars_iter=None):
        result = MagicMock()
        result.scalar = MagicMock(return_value=scalar_value)
        if scalars_iter is not None:
            scalars_mock = MagicMock()
            scalars_mock.__iter__ = lambda self: iter(scalars_iter)
            result.scalars = MagicMock(return_value=scalars_mock)
        return result

    async def fake_execute(_stmt):
        idx = call_index["n"]
        call_index["n"] += 1
        if idx == 0:
            return make_result(scalar_value=None)  # no prior consumption
        if idx == 1:
            return make_result(scalars_iter=[item])
        return make_result(scalars_iter=bom_items)

    async def fake_get(model_cls, ident):
        return materials_by_id.get(ident) if model_cls is Material else None

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.get = AsyncMock(side_effect=fake_get)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


async def _both(
    lines: list[Line],
    quantity: int = 1,
    *,
    order_currency: str = "UAH",
    fx: FxRates | None = None,
):
    """Run both services over the same recipe; return (preview envelope, booked).

    FX-CONVERSION: the SAME FxRates instance and the SAME target currency go to
    both sides. That is the whole point — it makes "preview and booked used one
    rate" structural rather than something the two code paths happen to agree on.
    """
    preview = await compute_bom_cost(
        _preview_db(lines),
        product_id=uuid.uuid4(),
        target_currency=order_currency,
        fx=fx,
    )

    product_id = uuid.uuid4()
    order = MagicMock()
    order.id = uuid.uuid4()
    order.currency = order_currency
    # WH-1: explicit, or the guard reads a truthy MagicMock and skips everything.
    order.computed_production_cost = None
    booked = await consume_materials_for_order(
        _consumption_db(lines, product_id, quantity), order, uuid.uuid4(), fx=fx
    )
    return preview, booked.computed_production_cost


# ── Parity ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_preview_equals_booked_with_waste():
    """The BOM-WASTE-1 regression: multi-line recipe, waste > 0, qty 1.

    Before the fix the preview omitted the waste factor entirely, so these two
    numbers differed by the whole waste allowance.
    """
    lines = [
        Line(qty="3.43", unit_cost="580.0000", waste="15.00"),
        Line(qty="0.75", unit_cost="123.4567", waste="7.50"),
        Line(qty="1.20", unit_cost="88.8888", waste="0.00"),
    ]
    preview, booked = await _both(lines)

    assert len(preview.basis) == 1
    assert preview.basis[0].currency == "UAH"
    assert preview.basis[0].amount == booked
    # Pinned so a drift in BOTH paths at once still fails.
    assert booked == Decimal("2494.01")


@pytest.mark.asyncio
async def test_preview_equals_booked_without_waste():
    """waste_percent = 0 everywhere → the fix must not move the number."""
    lines = [
        Line(qty="5.00", unit_cost="597.1400", waste="0.00"),
        Line(qty="1.00", unit_cost="45.0000", waste="0.00"),
    ]
    preview, booked = await _both(lines)

    assert preview.basis[0].amount == booked
    assert booked == Decimal("3030.70")  # 2985.70 + 45.00


@pytest.mark.asyncio
async def test_total_rounds_once_not_per_line():
    """Rounding granularity, not just rounding mode.

    Each line here rounds UP on its own (…5 in the third decimal), so summing
    per-line-rounded costs would give 2494.02. Both services must accumulate
    un-rounded and quantize once at the total — order_consumption_service.py
    :146-147,163-165 — giving 2494.01.
    """
    lines = [
        Line(qty="3.43", unit_cost="580.0000", waste="15.00"),
        Line(qty="0.75", unit_cost="123.4567", waste="7.50"),
        Line(qty="1.20", unit_cost="88.8888", waste="0.00"),
    ]
    preview, booked = await _both(lines)

    per_line_rounded = sum(
        (ln.qty * (Decimal("1") + ln.waste / Decimal("100")) * ln.unit_cost).quantize(
            Decimal("0.01")
        )
        for ln in lines
    )
    assert per_line_rounded == Decimal("2494.02"), "fixture must exercise the gap"
    assert preview.basis[0].amount == Decimal("2494.01") == booked


@pytest.mark.asyncio
async def test_rounding_mode_is_half_up():
    """An exact-half kopeck must round UP, matching the booked path.

    1.50 × 126.9500 = 190.425 exactly. ROUND_HALF_EVEN — the bare `.quantize()`
    default the preview used before — rounds to the even digit, 190.42, while
    the booked path's explicit ROUND_HALF_UP gives 190.43.
    """
    lines = [Line(qty="1.50", unit_cost="126.9500", waste="0.00")]
    preview, booked = await _both(lines)

    assert preview.basis[0].amount == Decimal("190.43") == booked


@pytest.mark.asyncio
async def test_parity_holds_per_currency_group():
    """Multi-currency recipes stay grouped in the basis, and with no rate
    configured the booked cost still degrades to None (task rule 4)."""
    lines = [
        Line(qty="2.00", unit_cost="100.0000", waste="10.00", currency="UAH"),
        Line(qty="1.00", unit_cost="50.0000", waste="0.00", currency="USD"),
    ]
    preview, booked = await _both(lines)

    by_currency = {row.currency: row.amount for row in preview.basis}
    assert by_currency == {"UAH": Decimal("220.00"), "USD": Decimal("50.00")}
    # No rate → the UAH group cannot reach UAH... it already is UAH, but the USD
    # group cannot be converted into it, so the whole rollup is skipped.
    assert booked is None
    assert preview.converted is None


# ── FX parity (FX-CONVERSION) ──────────────────────────────

FX = FxRates(uah_per_usd=Decimal("41.5"), source="manual")


@pytest.mark.asyncio
async def test_converted_preview_equals_booked_cogs():
    """The FX-CONVERSION equivalent of the BOM-WASTE-1 guard: what the operator
    reviews in USD must be exactly what a USD order books."""
    lines = [
        Line(qty="3.43", unit_cost="580.0000", waste="15.00"),
        Line(qty="0.75", unit_cost="123.4567", waste="7.50"),
        Line(qty="1.20", unit_cost="88.8888", waste="0.00"),
    ]
    preview, booked = await _both(lines, order_currency="USD", fx=FX)

    assert preview.converted is not None
    assert preview.converted.currency == "USD"
    assert preview.converted.converted_cost == booked
    # 2494.01 UAH / 41.5 = 60.0966... -> 60.10
    assert booked == Decimal("60.10")
    # The un-converted basis stays visible so the derivation is legible.
    assert preview.basis[0].amount == Decimal("2494.01")
    assert preview.converted.uah_per_usd == Decimal("41.5")


@pytest.mark.asyncio
async def test_conversion_rounds_once_across_buckets():
    """A repeating decimal, split over two currency buckets. Converting and
    rounding each bucket before summing would give a different kopeck."""
    lines = [
        Line(qty="1.00", unit_cost="100.0000", waste="0.00", currency="UAH"),
        Line(qty="1.00", unit_cost="2.0000", waste="0.00", currency="USD"),
    ]
    fx = FxRates(uah_per_usd=Decimal("3"), source="manual")
    preview, booked = await _both(lines, order_currency="USD", fx=fx)

    # 100/3 = 33.3333... plus 2.00 = 35.3333... -> 35.33
    assert preview.converted.converted_cost == booked == Decimal("35.33")


@pytest.mark.asyncio
async def test_same_currency_preview_reports_no_conversion():
    """A UAH recipe previewed for a UAH order was never converted, so claiming a
    conversion (and a rate) would be a fiction."""
    lines = [Line(qty="1.50", unit_cost="126.9500", waste="0.00")]
    preview, booked = await _both(lines, order_currency="UAH", fx=FX)

    assert preview.converted is None
    assert preview.basis[0].amount == booked == Decimal("190.43")


@pytest.mark.asyncio
async def test_unconvertible_currency_blocks_both_sides_identically():
    """An unsupported target degrades on BOTH paths — the preview must not show
    a number the booking will refuse to write."""
    lines = [Line(qty="2.00", unit_cost="100.0000", waste="10.00")]
    preview, booked = await _both(lines, order_currency="EUR", fx=FX)

    assert preview.converted is None
    assert booked is None


@pytest.mark.asyncio
async def test_untracked_line_prices_identically_in_preview_and_booking():
    """WH-1 — is_stock_tracked only decides whether stock moves, never what the
    line costs. compute_bom_cost does not read the flag at all, so if consumption
    ever skipped an untracked line's COST, this is where the two would diverge.
    """
    lines = [
        Line(qty="3.43", unit_cost="580.0000", waste="15.00"),
        Line(qty="1.00", unit_cost="25.0000", waste="0.00", is_stock_tracked=False),
    ]
    preview, booked = await _both(lines)

    assert preview.basis[0].amount == booked
    # 3.43 × 1.15 × 580 = 2287.81 (+) 25.00 — the service line is in the number.
    assert booked == Decimal("2312.81")
