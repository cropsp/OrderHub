"""WH-5 — retro-consumption backfill runner.

Validates services.consumption_backfill_service via mocked AsyncSession +
MagicMock objects, mirroring test_consumption_service.py (there are no TestClient
fixtures and no conftest.py in this repo).

Guards, in the order the sprint's verification list asks for them:
  1. Box resolution ①-⑤ — priority, the largest-volume rule and its tiebreakers,
     the shared-default case, and the mixed null/non-null case (a product with no
     default expresses no opinion, not a veto).
  2. The runner persists a resolved box onto order.packaging_id through
     update_order, so the mutation lands in order_status_history.
  3. A DRY RUN WRITES NOTHING — the service never commits and rolls the whole
     transaction back exactly once. This is the entire dry-run mechanism.
  4. Execute consumes through the real service and mirrors the four cost columns
     onto the order, exactly as change_order_status does.
  5. Idempotent re-run — the guard's skip also UNDOES the packaging_id write, so
     no order ever claims a box that was never consumed.
  6. Per-order failure isolation — one bad order cannot abort the batch.
  7. `statuses` may only name statuses that mean "physically shipped".
  8. OWNER-only.
  9. BOM-coverage parity with ConsumptionResult.partial_bom_coverage — the
     consumption service is untouched by this sprint, so a parity test is what
     keeps the runner's reading of "coverage" from drifting from the service's.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from models.bom import BomItem
from models.material import Material, MaterialMovement
from models.order import Order, OrderItem, OrderStatus, OrderStatusHistory
from models.packaging import PackagingBox
from models.product import Product
from models.user import UserRole
from schemas.warehouse import (
    RETRO_ELIGIBLE_STATUSES,
    BackfillOutcome,
    BomCoverage,
    BoxResolution,
    ConsumptionBackfillRequest,
)
from services import consumption_backfill_service
from services.consumption_backfill_service import (
    _bom_coverage,
    resolve_box_for_order,
    run_consumption_backfill,
)
from services.fx_service import FxRates

RATE = Decimal("41.5")


# ── Builders ───────────────────────────────────────────────


def _fx() -> FxRates:
    return FxRates(uah_per_usd=RATE, source="manual")


def _make_user(role=UserRole.OWNER):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    return user


def _make_material(
    *,
    name: str = "Шкіра",
    currency: str = "UAH",
    unit_cost: Decimal = Decimal("100"),
    stock: Decimal = Decimal("50"),
    is_active: bool = True,
    category: str = "MATERIAL",
) -> Material:
    material = Material(
        name=name,
        unit="dm2",
        currency=currency,
        current_unit_cost=unit_cost,
        stock_quantity=stock,
        low_stock_threshold=Decimal("0"),
        waste_percent=Decimal("0"),
        is_active=is_active,
        category=category,
        is_stock_tracked=True,
    )
    material.id = uuid.uuid4()
    return material


def _make_box(
    *,
    name: str,
    dims: tuple[int, int, int] = (100, 100, 100),
    max_weight_g: int = 5000,
    unit_cost: Decimal = Decimal("12"),
    stock: Decimal = Decimal("40"),
):
    """Box geometry + its paired Material. The Material is real so apply_movement
    can mutate its counter; the box is a MagicMock because only id, name, dims,
    max_weight_g and material_id/material are ever read."""
    material = _make_material(
        name=name, unit_cost=unit_cost, stock=stock, category="PACKAGING"
    )
    box = MagicMock()
    box.id = uuid.uuid4()
    box.name = name
    box.inner_length_mm, box.inner_width_mm, box.inner_height_mm = dims
    box.max_weight_g = max_weight_g
    box.material_id = material.id
    box.material = material
    return box


def _make_variant(product_id: uuid.UUID | None = None):
    variant = MagicMock()
    variant.product_id = product_id if product_id is not None else uuid.uuid4()
    return variant


def _make_item(*, variant, quantity: int = 1):
    item = MagicMock()
    item.variant = variant
    item.quantity = quantity
    return item


def _make_bom_item(*, material: Material, qty_per_unit: Decimal = Decimal("1")):
    bom = MagicMock()
    bom.qty_per_unit = qty_per_unit
    bom.material = material
    bom.material_id = material.id
    return bom


def _make_order(
    *,
    items: list | None = None,
    packaging_id: uuid.UUID | None = None,
    computed_packaging_box_id: uuid.UUID | None = None,
    computed_production_cost=None,
    currency: str = "UAH",
    status: OrderStatus = OrderStatus.SHIPPED,
    order_number: str | None = "TEST-1",
):
    order = MagicMock()
    order.id = uuid.uuid4()
    order.external_id = "ext-" + str(order.id)[:8]
    order.order_number = order_number
    order.currency = currency
    order.status = status
    order.ordered_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    order.items = items if items is not None else []
    order.shop = MagicMock()
    order.shop.name = "Lamamarka ETSY"
    # Both MUST be set explicitly: a bare MagicMock attribute is truthy, which
    # would silently turn every test here into an idempotent skip / a resolved box.
    order.packaging_id = packaging_id
    order.computed_packaging_box_id = computed_packaging_box_id
    order.computed_production_cost = computed_production_cost
    return order


def _entity_of(stmt):
    descriptions = stmt.column_descriptions
    return descriptions[0]["entity"] if descriptions else None


def _column_name_of(stmt):
    descriptions = stmt.column_descriptions
    return descriptions[0]["name"] if descriptions else None


def _bound_uuid(stmt):
    for value in stmt.compile().params.values():
        if isinstance(value, uuid.UUID):
            return value
    return None


def _result(*, scalars_iter=None, rows=None, scalar_value=None):
    result = MagicMock()
    result.scalar = MagicMock(return_value=scalar_value)
    result.all = MagicMock(return_value=list(rows or []))
    scalars_mock = MagicMock()
    values = list(scalars_iter or [])
    scalars_mock.__iter__ = lambda self: iter(values)
    scalars_mock.all = MagicMock(return_value=values)
    scalars_mock.unique = MagicMock(return_value=values)
    result.scalars = MagicMock(return_value=scalars_mock)
    return result


def _make_db(
    *,
    orders: list,
    boxes: list | None = None,
    product_defaults: dict | None = None,
    bom_lookup: dict | None = None,
    consumed_order_ids: set | None = None,
    fail_on_order_ids: set | None = None,
):
    """Mock AsyncSession dispatching on the ENTITY (and column) being queried.

    Anything unrecognised raises rather than falling through to a MagicMock —
    a silent MagicMock is how a harness fails open.
    """
    boxes = boxes or []
    product_defaults = product_defaults or {}
    bom_lookup = bom_lookup or {}
    consumed_order_ids = consumed_order_ids or set()
    fail_on_order_ids = fail_on_order_ids or set()

    boxes_by_id = {b.id: b for b in boxes}
    materials_by_id = {b.material.id: b.material for b in boxes}
    for lines in bom_lookup.values():
        for line in lines:
            materials_by_id[line.material.id] = line.material
    items_by_order = {o.id: list(o.items) for o in orders}

    added: list = []

    async def fake_execute(stmt):
        entity = _entity_of(stmt)
        if entity is PackagingBox:
            return _result(scalars_iter=boxes)
        if entity is Product:
            return _result(rows=list(product_defaults.items()))
        if entity is BomItem:
            # Two different BomItem queries, and they must not collide: the
            # runner's up-front `select(distinct(BomItem.product_id))` (labelled
            # "_no_label", no bind) versus the consumption service's per-product
            # `select(BomItem)` (labelled "BomItem"). Keying only on the entity is
            # what a first draft of this harness did, and it silently starved the
            # coverage set — caught by test_bom_coverage_matches_the_service.
            if _column_name_of(stmt) == "BomItem":
                return _result(scalars_iter=bom_lookup.get(_bound_uuid(stmt), []))
            return _result(scalars_iter=list(bom_lookup.keys()))
        if entity is Order:
            return _result(scalars_iter=orders)
        if entity is MaterialMovement:
            order_id = _bound_uuid(stmt)
            if order_id in fail_on_order_ids:
                raise RuntimeError("boom: simulated DB failure")
            return _result(
                scalar_value=(uuid.uuid4() if order_id in consumed_order_ids else None)
            )
        if entity is OrderItem:
            return _result(scalars_iter=items_by_order.get(_bound_uuid(stmt), []))
        raise AssertionError(
            f"Unexpected query against {entity!r} ({_column_name_of(stmt)!r}). "
            f"Teach this harness about it — do not let it fall through."
        )

    async def fake_get(model_cls, ident):
        if model_cls is Material:
            return materials_by_id.get(ident)
        if model_cls is PackagingBox:
            return boxes_by_id.get(ident)
        return None

    savepoint = AsyncMock()
    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.get = AsyncMock(side_effect=fake_get)
    db.add = MagicMock(side_effect=lambda obj: added.append(obj))
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.begin_nested = AsyncMock(return_value=savepoint)
    return db, added, savepoint


async def _run(db, *, user=None, dry_run=True, **kwargs):
    return await run_consumption_backfill(
        db,
        user=user or _make_user(),
        statuses=list(RETRO_ELIGIBLE_STATUSES),
        dry_run=dry_run,
        **kwargs,
    )


@pytest.fixture(autouse=True)
def _stub_fx(monkeypatch):
    """resolve() reads app settings; the runner's FX behaviour is the consumption
    service's, already covered there. Stub it so this harness need not model
    AppSetting rows."""
    monkeypatch.setattr(
        consumption_backfill_service.fx_service,
        "resolve",
        AsyncMock(return_value=_fx()),
    )


# ── 1. Box resolution (pure) ───────────────────────────────


def test_operator_choice_wins_over_everything():
    """① order.packaging_id is the operator's own decision and is never
    overwritten, even when the calculator and the products disagree."""
    chosen, other = uuid.uuid4(), uuid.uuid4()
    product_id = uuid.uuid4()
    order = _make_order(
        items=[_make_item(variant=_make_variant(product_id))],
        packaging_id=chosen,
        computed_packaging_box_id=other,
    )

    box_id, resolution = resolve_box_for_order(
        order, product_defaults={product_id: other}, boxes={}
    )

    assert box_id == chosen
    assert resolution is BoxResolution.ORDER_PACKAGING


def test_calculator_suggestion_beats_the_product_default():
    """② computed_packaging_box_id is already recorded on the order, so it
    outranks a catalogue-level default."""
    suggested, default = uuid.uuid4(), uuid.uuid4()
    product_id = uuid.uuid4()
    order = _make_order(
        items=[_make_item(variant=_make_variant(product_id))],
        computed_packaging_box_id=suggested,
    )

    box_id, resolution = resolve_box_for_order(
        order, product_defaults={product_id: default}, boxes={}
    )

    assert box_id == suggested
    assert resolution is BoxResolution.COMPUTED_BOX


def test_single_item_falls_back_to_the_product_default():
    product_id, default = uuid.uuid4(), uuid.uuid4()
    order = _make_order(items=[_make_item(variant=_make_variant(product_id))])

    box_id, resolution = resolve_box_for_order(
        order, product_defaults={product_id: default}, boxes={}
    )

    assert box_id == default
    assert resolution is BoxResolution.PRODUCT_DEFAULT


def test_several_products_sharing_one_default_is_not_ambiguous():
    """③, not ④ — three items, one box, nothing to choose between."""
    p1, p2, p3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    default = uuid.uuid4()
    order = _make_order(
        items=[
            _make_item(variant=_make_variant(p1)),
            _make_item(variant=_make_variant(p2)),
            _make_item(variant=_make_variant(p3)),
        ]
    )

    box_id, resolution = resolve_box_for_order(
        order,
        product_defaults={p1: default, p2: default, p3: default},
        boxes={},
    )

    assert box_id == default
    assert resolution is BoxResolution.PRODUCT_DEFAULT


def test_conflicting_defaults_take_the_largest_by_inner_volume():
    """④ one box per parcel (design §2.4): a box too small is a claim the parcel
    could not physically have been packed."""
    small = _make_box(name="Мала", dims=(100, 100, 50))
    large = _make_box(name="Велика", dims=(300, 200, 150))
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    order = _make_order(
        items=[
            _make_item(variant=_make_variant(p1)),
            _make_item(variant=_make_variant(p2)),
        ]
    )

    box_id, resolution = resolve_box_for_order(
        order,
        product_defaults={p1: small.id, p2: large.id},
        boxes={small.id: small, large.id: large},
    )

    assert box_id == large.id
    assert resolution is BoxResolution.PRODUCT_DEFAULT_LARGEST


def test_equal_volumes_break_on_capacity_then_name():
    """Deterministic, so a dry run and the execute run that follows it choose the
    same box. sort_order is deliberately not a key — the whole catalogue sits at
    its default 0, so it would decide nothing while looking like it did."""
    light = _make_box(name="Б-коробка", dims=(100, 100, 100), max_weight_g=3000)
    heavy = _make_box(name="А-коробка", dims=(100, 100, 100), max_weight_g=9000)
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    order = _make_order(
        items=[
            _make_item(variant=_make_variant(p1)),
            _make_item(variant=_make_variant(p2)),
        ]
    )
    boxes = {light.id: light, heavy.id: heavy}

    box_id, _ = resolve_box_for_order(
        order, product_defaults={p1: light.id, p2: heavy.id}, boxes=boxes
    )
    assert box_id == heavy.id, "higher capacity wins an equal-volume tie"

    # Same volume AND same capacity → name ascending.
    twin = _make_box(name="А-коробка-2", dims=(100, 100, 100), max_weight_g=9000)
    boxes[twin.id] = twin
    box_id, _ = resolve_box_for_order(
        order, product_defaults={p1: twin.id, p2: heavy.id}, boxes=boxes
    )
    assert box_id == heavy.id, "'А-коробка' sorts before 'А-коробка-2'"


def test_a_product_without_a_default_does_not_veto_the_others():
    """Sergii, WH-5 plan review: NULL is no opinion, not a veto. During runbook
    Phase 3 most orders are partially configured, and the strict reading would
    have starved the retro run of exactly those."""
    configured, unconfigured = uuid.uuid4(), uuid.uuid4()
    default = uuid.uuid4()
    order = _make_order(
        items=[
            _make_item(variant=_make_variant(configured)),
            _make_item(variant=_make_variant(unconfigured)),
        ]
    )

    box_id, resolution = resolve_box_for_order(
        order, product_defaults={configured: default}, boxes={}
    )

    assert box_id == default
    assert resolution is BoxResolution.PRODUCT_DEFAULT


def test_nothing_to_go_on_is_unresolved():
    """⑤ — no packaging consumption. BOM materials are still consumed; pickup and
    hand-delivered orders are real."""
    order = _make_order(items=[_make_item(variant=_make_variant())])

    box_id, resolution = resolve_box_for_order(
        order, product_defaults={}, boxes={}
    )

    assert box_id is None
    assert resolution is BoxResolution.UNRESOLVED


def test_items_without_a_product_link_contribute_nothing():
    """Manual / free-text line items, the same rule the consumption service uses."""
    free_text = _make_item(variant=None)
    orphan = _make_item(variant=_make_variant(None))
    order = _make_order(items=[free_text, orphan])

    box_id, resolution = resolve_box_for_order(
        order, product_defaults={}, boxes={}
    )

    assert (box_id, resolution) == (None, BoxResolution.UNRESOLVED)


# ── 2. Persisting the resolved box ─────────────────────────


@pytest.mark.asyncio
async def test_resolved_default_is_written_to_packaging_id_with_an_audit_row():
    """The write goes through order_service.update_order so the mutation lands in
    order_status_history exactly as a hand edit would — and so the consumption
    service needs no change at all to find the box."""
    box = _make_box(name="Коробка 100×120×50")
    product_id = uuid.uuid4()
    material = _make_material()
    order = _make_order(items=[_make_item(variant=_make_variant(product_id))])
    db, added, _ = _make_db(
        orders=[order],
        boxes=[box],
        product_defaults={product_id: box.id},
        bom_lookup={product_id: [_make_bom_item(material=material)]},
    )

    report = await _run(db, dry_run=False)

    assert order.packaging_id == box.id
    assert report.rows[0].packaging_id_written is True
    assert report.rows[0].resolution is BoxResolution.PRODUCT_DEFAULT

    history = [obj for obj in added if isinstance(obj, OrderStatusHistory)]
    assert len(history) == 1
    assert history[0].from_status == history[0].to_status == OrderStatus.SHIPPED.value
    assert history[0].comment.startswith("Fields updated: packaging_id:")
    assert str(box.id) in history[0].comment


@pytest.mark.asyncio
async def test_operator_choice_is_never_rewritten():
    box = _make_box(name="Коробка")
    order = _make_order(
        items=[_make_item(variant=_make_variant())], packaging_id=box.id
    )
    db, added, _ = _make_db(orders=[order], boxes=[box])

    report = await _run(db, dry_run=False)

    assert report.rows[0].packaging_id_written is False
    assert not [obj for obj in added if isinstance(obj, OrderStatusHistory)]


# ── 3. A dry run writes nothing ────────────────────────────


@pytest.mark.asyncio
async def test_dry_run_rolls_the_transaction_back_and_never_commits():
    """The ENTIRE dry-run mechanism. Nothing on this path commits, so discarding
    the transaction discards every movement, cost snapshot, packaging_id and audit
    row the run staged. If this test ever fails, a dry run has become a live one."""
    box = _make_box(name="Коробка")
    product_id = uuid.uuid4()
    order = _make_order(items=[_make_item(variant=_make_variant(product_id))])
    db, _, _ = _make_db(
        orders=[order],
        boxes=[box],
        product_defaults={product_id: box.id},
        bom_lookup={product_id: [_make_bom_item(material=_make_material())]},
    )

    report = await _run(db, dry_run=True)

    assert report.dry_run is True
    assert report.orders_consumed == 1, "the work is really done, then discarded"
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_does_not_roll_back():
    """A real run commits via get_db on return, like every other backfill."""
    order = _make_order(items=[_make_item(variant=_make_variant())])
    db, _, _ = _make_db(orders=[order])

    await _run(db, dry_run=False)

    db.rollback.assert_not_awaited()
    db.commit.assert_not_awaited()


# ── 4. Execute books through the real service ──────────────


@pytest.mark.asyncio
async def test_execute_consumes_and_mirrors_the_four_cost_columns():
    """The consumption service does not write these; its caller always has, and
    they move together or not at all (order_service.change_order_status)."""
    material = _make_material(unit_cost=Decimal("100"), stock=Decimal("50"))
    box = _make_box(name="Коробка", unit_cost=Decimal("12"))
    product_id = uuid.uuid4()
    order = _make_order(
        items=[_make_item(variant=_make_variant(product_id), quantity=2)],
        currency="UAH",
    )
    db, added, _ = _make_db(
        orders=[order],
        boxes=[box],
        product_defaults={product_id: box.id},
        bom_lookup={product_id: [_make_bom_item(material=material, qty_per_unit=Decimal("1"))]},
    )

    report = await _run(db, dry_run=False)
    row = report.rows[0]

    # 2 units × 100 (material) + 12 (one box per parcel, never per product).
    assert order.computed_production_cost == Decimal("212.00")
    assert row.backfill_production_cost == Decimal("212.00")
    assert order.cogs_basis_amount == Decimal("212.0000")
    assert order.cogs_basis_currency == "UAH"
    assert row.packaging_consumed is True
    assert row.outcome is BackfillOutcome.CONSUMED

    movements = [obj for obj in added if isinstance(obj, MaterialMovement)]
    assert len(movements) == 2, "one BOM line + the box"
    assert material.stock_quantity == Decimal("48")
    assert box.material.stock_quantity == Decimal("39")

    assert [(t.currency, t.backfill_production_cost_total, t.orders) for t in report.cost_totals] == [
        ("UAH", Decimal("212.00"), 1)
    ]
    assert [(b.box_id, b.units) for b in report.boxes_consumed] == [(box.id, 1)]


@pytest.mark.asyncio
async def test_an_order_with_no_bom_consumes_the_box_but_books_no_cost():
    """WH-2 rule ①, unchanged by the runner: a box-only cost would win the row-wise
    COALESCE in five aggregates and replace a hand-entered production_cost."""
    box = _make_box(name="Коробка")
    product_id = uuid.uuid4()
    order = _make_order(items=[_make_item(variant=_make_variant(product_id))])
    db, _, _ = _make_db(
        orders=[order],
        boxes=[box],
        product_defaults={product_id: box.id},
        bom_lookup={},
    )

    report = await _run(db, dry_run=False)
    row = report.rows[0]

    assert row.bom_coverage is BomCoverage.NONE
    assert row.backfill_production_cost is None
    assert order.computed_production_cost is None
    assert row.packaging_consumed is True
    assert any("not costed" in w for w in row.warnings)
    assert report.orders_without_bom == [order.order_number]
    assert report.cost_totals == []


@pytest.mark.asyncio
async def test_unresolved_box_still_consumes_bom_materials():
    material = _make_material()
    product_id = uuid.uuid4()
    order = _make_order(items=[_make_item(variant=_make_variant(product_id))])
    db, added, _ = _make_db(
        orders=[order],
        bom_lookup={product_id: [_make_bom_item(material=material)]},
    )

    report = await _run(db, dry_run=False)
    row = report.rows[0]

    assert row.resolution is BoxResolution.UNRESOLVED
    assert row.packaging_consumed is False
    assert row.backfill_production_cost == Decimal("100.00")
    assert report.orders_without_box == [order.order_number]
    assert len([obj for obj in added if isinstance(obj, MaterialMovement)]) == 1


# ── 5. Idempotency ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_already_consumed_order_is_skipped_and_its_box_write_undone():
    """The runner cannot know in advance whether the guard will fire — only the
    service can. So the write happens first and the savepoint is rolled back on a
    skip, which keeps the guard as the single source of truth while never leaving
    an order claiming a box that was never consumed."""
    box = _make_box(name="Коробка")
    product_id = uuid.uuid4()
    order = _make_order(items=[_make_item(variant=_make_variant(product_id))])
    db, _, savepoint = _make_db(
        orders=[order],
        boxes=[box],
        product_defaults={product_id: box.id},
        consumed_order_ids={order.id},
    )

    report = await _run(db, dry_run=False)
    row = report.rows[0]

    assert row.outcome is BackfillOutcome.ALREADY_CONSUMED
    assert row.packaging_id_written is False
    savepoint.rollback.assert_awaited_once()
    savepoint.commit.assert_not_awaited()
    assert report.orders_already_consumed == 1
    assert report.orders_consumed == 0
    assert report.boxes_consumed == []


@pytest.mark.asyncio
async def test_a_booked_cost_alone_blocks_a_re_run():
    """WH-1's second probe: an all-untracked recipe leaves no ledger row, so the
    movement probe alone would let a re-run re-price a frozen snapshot."""
    order = _make_order(
        items=[_make_item(variant=_make_variant())],
        computed_production_cost=Decimal("500.00"),
    )
    db, _, _ = _make_db(orders=[order])

    report = await _run(db, dry_run=False)

    assert report.rows[0].outcome is BackfillOutcome.ALREADY_CONSUMED
    assert order.computed_production_cost == Decimal("500.00")


# ── 6. Failure isolation ───────────────────────────────────


@pytest.mark.asyncio
async def test_one_bad_order_cannot_abort_the_batch():
    material = _make_material()
    product_id = uuid.uuid4()
    good_a = _make_order(
        items=[_make_item(variant=_make_variant(product_id))], order_number="A"
    )
    bad = _make_order(
        items=[_make_item(variant=_make_variant(product_id))], order_number="B"
    )
    good_b = _make_order(
        items=[_make_item(variant=_make_variant(product_id))], order_number="C"
    )
    db, _, savepoint = _make_db(
        orders=[good_a, bad, good_b],
        bom_lookup={product_id: [_make_bom_item(material=material)]},
        fail_on_order_ids={bad.id},
    )

    report = await _run(db, dry_run=False)

    assert report.orders_total == 3
    assert report.orders_consumed == 2
    assert report.orders_failed == 1
    failed = [r for r in report.rows if r.outcome is BackfillOutcome.FAILED]
    assert [r.order_number for r in failed] == ["B"]
    assert "boom" in failed[0].error
    savepoint.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_failure_reports_the_http_detail_not_the_repr():
    """apply_movement answers 422/404 as HTTPException; str(exc) on one of those is
    an unhelpful blob, and the detail is the sentence a human needs."""
    product_id = uuid.uuid4()
    order = _make_order(items=[_make_item(variant=_make_variant(product_id))])
    db, _, _ = _make_db(orders=[order], bom_lookup={product_id: []})
    original = db.execute.side_effect

    async def explode(stmt):
        if _entity_of(stmt) is OrderItem:
            raise HTTPException(status_code=422, detail="unit_cost_at_movement is required")
        return await original(stmt)

    db.execute = AsyncMock(side_effect=explode)

    report = await _run(db, dry_run=False)

    assert report.rows[0].error == "unit_cost_at_movement is required"


# ── 7. Eligible statuses ───────────────────────────────────


def test_statuses_default_to_the_two_that_mean_shipped():
    assert RETRO_ELIGIBLE_STATUSES == (OrderStatus.SHIPPED, OrderStatus.COMPLETED)
    assert ConsumptionBackfillRequest().statuses is None


@pytest.mark.parametrize(
    "given, expected",
    [
        (["shipped"], [OrderStatus.SHIPPED]),
        (["SHIPPED"], [OrderStatus.SHIPPED]),
        (["completed", "shipped"], [OrderStatus.COMPLETED, OrderStatus.SHIPPED]),
    ],
)
def test_statuses_accept_names_or_values(given, expected):
    """Driven by hand from a terminal, and the DB stores the member NAMES while
    Pydantic parses by value — accept both rather than making that a trap."""
    assert ConsumptionBackfillRequest(statuses=given).statuses == expected


@pytest.mark.parametrize("given", [["in_production"], ["cancelled"], ["new"], []])
def test_statuses_outside_the_shipped_set_are_rejected(given):
    """Consuming for an order that never shipped would move stock that never left
    the shelf."""
    with pytest.raises(ValidationError):
        ConsumptionBackfillRequest(statuses=given)


def test_unknown_body_fields_are_a_loud_422():
    with pytest.raises(ValidationError):
        ConsumptionBackfillRequest(dryrun=False)


# ── 8. OWNER-only ──────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.DESIGNER])
async def test_non_owner_roles_are_rejected(role):
    """The MCP agent authenticates as a MANAGER — this endpoint is deliberately
    out of its reach. Exercised through the dependency itself, since calling the
    coroutine directly bypasses FastAPI's dependency injection."""
    from routers.dependencies import require_role

    checker = require_role(UserRole.OWNER)
    with pytest.raises(HTTPException) as exc:
        await checker(current_user=_make_user(role=role))

    assert exc.value.status_code == 403


def test_the_route_is_wired_to_the_owner_gate():
    """The parametrized test above proves require_role(OWNER) refuses; this proves
    the route actually carries it."""
    import main
    from fastapi.routing import APIRoute

    route = next(
        r
        for r in main.app.routes
        if isinstance(r, APIRoute) and r.path == "/api/warehouse/backfill-consumption"
    )
    role_sets = [
        dep.dependency.__closure__[0].cell_contents
        for dep in route.dependencies
        if getattr(dep.dependency, "__name__", "") == "role_checker"
    ]
    assert role_sets == [(UserRole.OWNER,)]


# ── 9. BOM-coverage parity with the consumption service ────


@pytest.mark.parametrize(
    "equipped, total, expected",
    [
        (0, 0, BomCoverage.NONE),
        (0, 2, BomCoverage.NONE),
        (1, 2, BomCoverage.PARTIAL),
        (2, 2, BomCoverage.FULL),
    ],
)
def test_bom_coverage_classification(equipped, total, expected):
    with_bom = [uuid.uuid4() for _ in range(equipped)]
    without = [uuid.uuid4() for _ in range(total - equipped)]
    order = _make_order(
        items=[_make_item(variant=_make_variant(p)) for p in with_bom + without]
    )

    assert _bom_coverage(order, set(with_bom)) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("equipped_products", [0, 1, 2])
async def test_bom_coverage_matches_the_service(equipped_products):
    """order_consumption_service is untouched by this sprint (task rule 9), so the
    runner re-derives coverage instead of extending ConsumptionResult. This pins
    the two readings together — the same job test_bom_waste_parity.py does for
    bom_service."""
    products = [uuid.uuid4(), uuid.uuid4()]
    equipped = products[:equipped_products]
    order = _make_order(
        items=[_make_item(variant=_make_variant(p)) for p in products]
    )
    db, _, _ = _make_db(
        orders=[order],
        bom_lookup={p: [_make_bom_item(material=_make_material())] for p in equipped},
    )

    report = await _run(db, dry_run=False)
    coverage = report.rows[0].bom_coverage

    # The service's own verdict, recomputed from the same order.
    from services.order_consumption_service import consume_materials_for_order

    db2, _, _ = _make_db(
        orders=[order],
        bom_lookup={p: [_make_bom_item(material=_make_material())] for p in equipped},
    )
    order.computed_production_cost = None
    result = await consume_materials_for_order(db2, order, uuid.uuid4(), fx=_fx())

    assert (coverage is BomCoverage.PARTIAL) == result.partial_bom_coverage


# ── Reporting shape ────────────────────────────────────────


@pytest.mark.asyncio
async def test_report_counts_partition_the_orders_examined():
    """orders_total == consumed + already + failed, always — the first thing a
    reader of the dry-run report checks."""
    material = _make_material()
    product_id = uuid.uuid4()
    fresh = _make_order(items=[_make_item(variant=_make_variant(product_id))], order_number="A")
    done = _make_order(items=[_make_item(variant=_make_variant(product_id))], order_number="B")
    broken = _make_order(items=[_make_item(variant=_make_variant(product_id))], order_number="C")
    db, _, _ = _make_db(
        orders=[fresh, done, broken],
        bom_lookup={product_id: [_make_bom_item(material=material)]},
        consumed_order_ids={done.id},
        fail_on_order_ids={broken.id},
    )

    report = await _run(db, dry_run=True)

    assert report.orders_total == 3
    assert (
        report.orders_consumed
        + report.orders_already_consumed
        + report.orders_failed
        == report.orders_total
    )
    assert len(report.rows) == 3


@pytest.mark.asyncio
async def test_ambiguous_multi_default_orders_are_flagged_for_review():
    small = _make_box(name="Мала", dims=(100, 100, 50))
    large = _make_box(name="Велика", dims=(300, 200, 150))
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    order = _make_order(
        items=[
            _make_item(variant=_make_variant(p1)),
            _make_item(variant=_make_variant(p2)),
        ],
        order_number="AMBIG-1",
    )
    db, _, _ = _make_db(
        orders=[order],
        boxes=[small, large],
        product_defaults={p1: small.id, p2: large.id},
        bom_lookup={p1: [_make_bom_item(material=_make_material())]},
    )

    report = await _run(db, dry_run=True)

    assert report.rows[0].resolution is BoxResolution.PRODUCT_DEFAULT_LARGEST
    assert report.rows[0].resolved_box_name == "Велика"
    assert report.orders_ambiguous_default == ["AMBIG-1"]


@pytest.mark.asyncio
async def test_etsy_and_manual_orders_are_labelled_by_external_id():
    """order_number is NULL for everything that is not a Shopify order."""
    order = _make_order(
        items=[_make_item(variant=_make_variant())], order_number=None
    )
    db, _, _ = _make_db(orders=[order])

    report = await _run(db, dry_run=True)

    assert report.orders_without_box == [order.external_id]
