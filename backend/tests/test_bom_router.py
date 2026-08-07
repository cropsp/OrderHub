"""MAT-3 — BOM router / service regression-guards.

Mirrors the compile-SQL pattern from test_materials_router.py. Captures
DELETE / SELECT statements via a mocked AsyncSession.execute and asserts on
the compiled SQL string. Behavioral tests construct Pydantic payloads or
mock the joined Material relationship to drive the read projection.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from schemas.bom import BomItemCreate, BomReplaceRequest
from services import bom_service


def _make_db():
    """AsyncSession mock that captures statements and added instances."""
    captured_stmts: list = []
    captured_adds: list = []

    async def fake_execute(stmt):
        captured_stmts.append(stmt)
        r = MagicMock()
        # Default: no existing BomItems, no matching materials. Tests that
        # need otherwise replace `db.execute.side_effect`.
        r.scalars.return_value.all.return_value = []
        r.all.return_value = []
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.add = MagicMock(side_effect=lambda obj: captured_adds.append(obj))
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    return db, captured_stmts, captured_adds


def _compiled(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()


@pytest.mark.asyncio
async def test_replace_bom_deletes_existing_and_inserts_new():
    """PUT /api/products/{id}/bom with new items → service emits one
    DELETE filtered by product_id, then bulk-inserts each item via db.add."""
    db, stmts, adds = _make_db()
    product_id = uuid.uuid4()
    mat_a, mat_b = uuid.uuid4(), uuid.uuid4()

    # Two queued execute() results: existing material_ids (empty),
    # then the Material lookup → return two active Materials.
    existing_result = MagicMock()
    existing_result.scalars.return_value.all.return_value = []
    material_a = MagicMock(id=mat_a, is_active=True, name="A")
    material_b = MagicMock(id=mat_b, is_active=True, name="B")
    materials_result = MagicMock()
    materials_result.scalars.return_value.all.return_value = [material_a, material_b]
    delete_result = MagicMock()
    # final get_bom() reload — no rows captured because we don't simulate inserts.
    reload_result = MagicMock()
    reload_result.scalars.return_value.all.return_value = []

    queue = [existing_result, materials_result, delete_result, reload_result]

    async def staged_execute(stmt):
        stmts.append(stmt)
        return queue.pop(0)

    db.execute = AsyncMock(side_effect=staged_execute)

    items = [
        BomItemCreate(material_id=mat_a, qty_per_unit=Decimal("5.00"), notes=None),
        BomItemCreate(material_id=mat_b, qty_per_unit=Decimal("1.00"), notes=None),
    ]
    await bom_service.replace_bom(db, product_id=product_id, items=items)

    # 3rd captured stmt is the DELETE (after existing-lookup SELECT + materials SELECT).
    delete_sql = _compiled(stmts[2])
    assert "delete from bom_items" in delete_sql, (
        f"replace_bom must emit DELETE on bom_items. SQL: {delete_sql}"
    )
    assert "bom_items.product_id" in delete_sql, (
        f"DELETE must filter by product_id. SQL: {delete_sql}"
    )

    # Bulk insert via db.add — one call per item.
    assert len(adds) == 2, f"expected 2 db.add calls, got {len(adds)}"
    staged_ids = {item.material_id for item in adds}
    assert staged_ids == {mat_a, mat_b}


def test_replace_bom_rejects_duplicate_material_in_payload():
    """BomReplaceRequest with two items sharing the same material_id raises
    ValidationError at Pydantic level — before the service is invoked."""
    mat = uuid.uuid4()
    with pytest.raises(ValidationError) as exc_info:
        BomReplaceRequest(
            items=[
                BomItemCreate(material_id=mat, qty_per_unit=Decimal("5.00"), notes=None),
                BomItemCreate(material_id=mat, qty_per_unit=Decimal("2.00"), notes=None),
            ]
        )
    assert "duplicate material_id" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_compute_bom_cost_selects_the_costing_columns():
    """compute_bom_cost joins materials and projects the four columns its
    Python fold needs — including waste_percent (BOM-WASTE-1)."""
    db, stmts, _adds = _make_db()
    await bom_service.compute_bom_cost(db, product_id=uuid.uuid4())

    assert len(stmts) == 1, f"expected exactly 1 statement, got {len(stmts)}"
    sql = _compiled(stmts[0])
    assert "join materials" in sql, f"must JOIN materials. SQL: {sql}"
    for column in ("current_unit_cost", "waste_percent", "qty_per_unit", "currency"):
        assert column in sql, f"must project materials.{column}. SQL: {sql}"


@pytest.mark.asyncio
async def test_compute_bom_cost_groups_by_currency():
    """The fold buckets per material currency and rounds each bucket once.

    Behavioural rather than SQL-shape: BOM-WASTE-1 moved the arithmetic out of
    func.sum() into Python so it performs the same Decimal operations, in the
    same order, as the consumption path (see test_bom_waste_parity.py).
    """
    db, _stmts, _adds = _make_db()
    # (currency, qty_per_unit, current_unit_cost, waste_percent)
    rows = [
        ("UAH", Decimal("2.00"), Decimal("100.0000"), Decimal("10.00")),
        ("UAH", Decimal("1.00"), Decimal("50.0000"), Decimal("0.00")),
        ("USD", Decimal("3.00"), Decimal("10.0000"), Decimal("50.00")),
    ]
    result = MagicMock()
    result.all.return_value = rows
    db.execute = AsyncMock(return_value=result)

    envelope = await bom_service.compute_bom_cost(db, product_id=uuid.uuid4())

    by_currency = {row.currency: row.amount for row in envelope.basis}
    assert by_currency == {
        "UAH": Decimal("270.00"),  # 2×1.10×100 + 1×1.00×50
        "USD": Decimal("45.00"),  # 3×1.50×10
    }


@pytest.mark.asyncio
async def test_compute_bom_cost_empty_recipe_returns_no_rows():
    """A product with no BOM yields an empty breakdown, not a zero row."""
    db, _stmts, _adds = _make_db()
    envelope = await bom_service.compute_bom_cost(db, product_id=uuid.uuid4())

    assert envelope.basis == []
    # FX-CONVERSION: nothing to convert, so no converted block either — a 0.00
    # USD figure would read as "this recipe is free".
    assert envelope.converted is None


@pytest.mark.asyncio
async def test_compute_bom_cost_without_a_target_currency_does_not_convert():
    """Omitting ?in= keeps the pre-FX behaviour exactly: basis only."""
    db, _stmts, _adds = _make_db()
    result = MagicMock()
    result.all.return_value = [
        ("UAH", Decimal("2.00"), Decimal("100.0000"), Decimal("0.00")),
    ]
    db.execute = AsyncMock(return_value=result)

    envelope = await bom_service.compute_bom_cost(db, product_id=uuid.uuid4())

    assert envelope.basis[0].amount == Decimal("200.00")
    assert envelope.converted is None


def test_project_bom_item_flags_inactive_material():
    """A BomItem whose joined Material has is_active=False is projected with
    material_is_active=False — the editor uses this to render the amber
    Discontinued badge + recipe-level warning banner."""
    inactive_mat = MagicMock(
        name="Фанера 4mm",
        unit="m2",
        currency="UAH",
        current_unit_cost=Decimal("0"),
        waste_percent=Decimal("0"),
        is_active=False,
    )
    # MagicMock auto-creates a `name` attribute that shadows the kwarg —
    # set it explicitly so the projection picks up the real string.
    inactive_mat.name = "Фанера 4mm"

    bom_item = MagicMock()
    bom_item.id = uuid.uuid4()
    bom_item.product_id = uuid.uuid4()
    bom_item.material_id = uuid.uuid4()
    bom_item.qty_per_unit = Decimal("0.50")
    bom_item.notes = None
    bom_item.material = inactive_mat

    projection = bom_service.project_bom_item(bom_item)
    assert projection.material_is_active is False
    assert projection.material_name == "Фанера 4mm"
    assert projection.line_cost == Decimal("0.00")


def test_project_bom_item_line_cost_includes_waste():
    """BOM-WASTE-1: the per-line cost the operator reviews carries the same
    waste allowance shipment books, and waste_percent rides along so the editor
    can price a draft row whose material is soft-deleted."""
    mat = MagicMock(
        unit="dm2",
        currency="UAH",
        current_unit_cost=Decimal("580.0000"),
        waste_percent=Decimal("15.00"),
        is_active=True,
    )
    mat.name = "Шкіра італійська чорна"

    bom_item = MagicMock()
    bom_item.id = uuid.uuid4()
    bom_item.product_id = uuid.uuid4()
    bom_item.material_id = uuid.uuid4()
    bom_item.qty_per_unit = Decimal("0.13")
    bom_item.notes = None
    bom_item.material = mat

    projection = bom_service.project_bom_item(bom_item)
    assert projection.material_waste_percent == Decimal("15.00")
    # 0.13 × 1.15 × 580.00 = 86.71 — not the 75.40 the waste-free path gave.
    assert projection.line_cost == Decimal("86.71")


# ── USER-ACCESS-2 x FX-CONVERSION: censoring the converted block ──


@pytest.mark.asyncio
async def test_bom_response_nulls_the_converted_cost_without_view_costs():
    """The FX conversion is a cost figure and must be censored like one.

    _strip_bom_costs (routers/products.py) is a hardcoded two-field list covering
    only per-line costs, which is exactly why no converted figure is ever placed
    on BomItemRead — it would slip past that list. The envelope-level block is
    dropped here instead, and this test is what keeps that true.
    """
    from routers import products as products_router

    db = MagicMock()
    with patch.object(
        products_router, "_can_view_costs", AsyncMock(return_value=False)
    ), patch.object(
        products_router.bom_service, "compute_bom_cost", AsyncMock()
    ) as compute, patch.object(
        products_router.fx_service, "resolve", AsyncMock()
    ):
        response = await products_router._bom_response(
            db, uuid.uuid4(), [], False, MagicMock(), target_currency="USD"
        )

    assert response.cost == []
    assert response.cost_converted is None
    # Not merely nulled after the fact — never computed for this caller.
    compute.assert_not_awaited()


@pytest.mark.asyncio
async def test_bom_response_passes_the_target_currency_through_with_view_costs():
    from routers import products as products_router
    from schemas.bom import BomCostConverted, BomCostEnvelope

    converted = BomCostConverted(
        currency="USD",
        converted_cost=Decimal("60.10"),
        uah_per_usd=Decimal("41.5"),
    )
    db = MagicMock()
    with patch.object(
        products_router, "_can_view_costs", AsyncMock(return_value=True)
    ), patch.object(
        products_router.bom_service,
        "compute_bom_cost",
        AsyncMock(return_value=BomCostEnvelope(basis=[], converted=converted)),
    ) as compute, patch.object(
        products_router.fx_service, "resolve", AsyncMock()
    ):
        response = await products_router._bom_response(
            db, uuid.uuid4(), [], False, MagicMock(), target_currency="USD"
        )

    assert response.cost_converted is converted
    assert compute.await_args.kwargs["target_currency"] == "USD"


# ---------------------------------------------------------------------------
# WH-1 — non-stock flag on the projection; packaging is not a recipe line
# ---------------------------------------------------------------------------

def _projectable(**material_attrs):
    mat = MagicMock()
    mat.name = material_attrs.pop("name", "Матеріал")
    mat.unit = "dm2"
    mat.currency = "UAH"
    mat.current_unit_cost = Decimal("0")
    mat.waste_percent = Decimal("0")
    mat.is_active = True
    mat.is_stock_tracked = True
    for key, value in material_attrs.items():
        setattr(mat, key, value)

    bom_item = MagicMock()
    bom_item.id = uuid.uuid4()
    bom_item.product_id = uuid.uuid4()
    bom_item.material_id = uuid.uuid4()
    bom_item.qty_per_unit = Decimal("1.00")
    bom_item.notes = None
    bom_item.material = mat
    return bom_item


def test_project_bom_item_carries_the_non_stock_flag():
    """The editor renders a visible hint from this; a dropped field would turn
    the exception back into a silent one."""
    projection = bom_service.project_bom_item(
        _projectable(name="Лазерна порізка", is_stock_tracked=False)
    )
    assert projection.material_is_stock_tracked is False


def test_project_bom_item_normalises_an_unset_flag_to_true():
    """The column is NOT NULL, but a Material that has not been flushed reads
    None — and None on a `bool` field would 500 the whole BOM read."""
    projection = bom_service.project_bom_item(_projectable(is_stock_tracked=None))
    assert projection.material_is_stock_tracked is True


def _materials_result(materials: list):
    r = MagicMock()
    r.scalars.return_value.all.return_value = materials
    return r


def _replace_bom_db(existing_ids: list, materials: list):
    """execute() answers the prior-recipe query first, then the material lookup."""
    calls = {"n": 0}

    async def fake_execute(_stmt):
        calls["n"] += 1
        r = MagicMock()
        if calls["n"] == 1:
            r.scalars.return_value.all.return_value = existing_ids
        else:
            r.scalars.return_value.all.return_value = materials
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _material_row(material_id, *, category="MATERIAL", name="Матеріал"):
    mat = MagicMock()
    mat.id = material_id
    mat.name = name
    mat.is_active = True
    mat.category = category
    return mat


@pytest.mark.asyncio
async def test_replace_bom_rejects_a_packaging_material():
    """A box is one per PARCEL, not per product (DESIGN §2.4). Enforced in the
    service, not just the picker, because this is also the MCP agent's write
    path — and in WH-1 a packaging line would decrement the material counter at
    SHIPPED while shipping.py still decrements the box counter at TTN."""
    material_id = uuid.uuid4()
    db = _replace_bom_db(
        existing_ids=[],
        materials=[_material_row(material_id, category="PACKAGING", name="100x120x50")],
    )

    with pytest.raises(HTTPException) as exc:
        await bom_service.replace_bom(
            db,
            product_id=uuid.uuid4(),
            items=[BomItemCreate(material_id=material_id, qty_per_unit=Decimal("1"))],
        )

    assert exc.value.status_code == 422
    assert "packaging" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_replace_bom_grandfathers_a_packaging_material_already_in_the_recipe():
    """Same rule as discontinued materials: a recipe that already contains one
    stays editable, so an operator is never locked out of their own product."""
    material_id = uuid.uuid4()
    db = _replace_bom_db(
        existing_ids=[material_id],
        materials=[_material_row(material_id, category="PACKAGING")],
    )

    # get_bom is called at the end; stub it out — this test is about validation.
    with patch.object(
        bom_service, "get_bom", AsyncMock(return_value=([], False))
    ):
        await bom_service.replace_bom(
            db,
            product_id=uuid.uuid4(),
            items=[BomItemCreate(material_id=material_id, qty_per_unit=Decimal("1"))],
        )
