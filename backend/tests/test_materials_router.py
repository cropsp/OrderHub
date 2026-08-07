"""MAT-1 — Materials router regression-guards.

Mirrors the compile-SQL pattern from test_finance_router.py / test_dashboard_router.py.
Captures SELECT statements via a mocked AsyncSession.execute and asserts on the
compiled SQL string. For the create path, captures `db.add(...)` to verify the
ORM instance carries the user-supplied `currency` value through to persistence.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from models.material import Material, MaterialMovement, MaterialMovementReason
from routers.materials import (
    update_material,
    create_material,
    list_material_movements,
    list_materials,
)
from schemas.material import MaterialCreate


def _make_db():
    """AsyncSession mock that captures statements through execute() and
    instances through add()."""
    captured_stmts: list = []
    captured_adds: list = []

    async def fake_execute(stmt):
        captured_stmts.append(stmt)
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
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
        stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()


@pytest.mark.asyncio
async def test_create_material_persists_currency():
    """POST /api/materials with currency='UAH' → the Material instance staged for
    persistence carries that currency. Catches accidental drops or coercions of
    the field before it ever reaches the DB."""
    db, _stmts, adds = _make_db()
    body = MaterialCreate(
        name="Шкіра італійська чорна",
        unit="dm2",
        currency="UAH",
        supplier_name=None,
        notes=None,
    )

    await create_material(body=body, db=db, user=MagicMock())

    assert len(adds) == 1, f"expected 1 db.add call, got {len(adds)}"
    staged = adds[0]
    assert isinstance(staged, Material)
    assert staged.currency == "UAH", (
        f"Material was staged with currency={staged.currency!r}; expected 'UAH'."
    )
    assert staged.name == "Шкіра італійська чорна"
    assert staged.unit == "dm2"


@pytest.mark.asyncio
async def test_create_material_persists_supplier_sku():
    """MAT-6 — the supplier article reaches the staged Material. It is the dedup
    key that ties one material across invoices, so a silent drop here would leave
    every new material unmatchable."""
    db, _stmts, adds = _make_db()
    body = MaterialCreate(
        name="Шкіра Крейзі Хорс AN 1,4-1,6мм чорна",
        unit="dm2",
        currency="UAH",
        supplier_name="ФОП Додон Максим Анатолійович",
        supplier_sku="027515",
        notes=None,
    )

    await create_material(body=body, db=db, user=MagicMock())

    staged = adds[0]
    assert staged.supplier_sku == "027515", (
        f"Material was staged with supplier_sku={staged.supplier_sku!r}; expected '027515'."
    )


@pytest.mark.asyncio
async def test_create_material_without_supplier_sku_is_null():
    """Nullable by design — non-catalog items (some hardware, thread) have no
    supplier code, and 2 of the 15 materials loaded so far carry none."""
    db, _stmts, adds = _make_db()
    body = MaterialCreate(name="Нитка", unit="m", currency="UAH")

    await create_material(body=body, db=db, user=MagicMock())

    assert adds[0].supplier_sku is None


@pytest.mark.asyncio
async def test_list_materials_search_matches_name_and_supplier_sku():
    """MAT-6 — `search` must hit supplier_sku server-side, not just name.

    The MCP create-time dedup guard searches by SKU and then exact-matches
    client-side; if the server only matched names the guard would silently never
    fire, which is the failure this column exists to prevent."""
    db, stmts, _adds = _make_db()

    await list_materials(
        search="027515", include_inactive=False, category=None, db=db, user=MagicMock()
    )
    sql = _compiled(stmts[-1])

    # literal_binds escapes the LIKE wildcards as '%%'.
    assert "materials.name ilike '%%027515%%'" in sql, (
        f"search must still match the name. SQL: {sql}"
    )
    assert "materials.supplier_sku ilike '%%027515%%'" in sql, (
        f"search must also match supplier_sku. SQL: {sql}"
    )
    assert (
        "materials.name ilike '%%027515%%' or materials.supplier_sku ilike '%%027515%%'"
        in sql
    ), f"name and supplier_sku must be OR-ed, not AND-ed. SQL: {sql}"


@pytest.mark.asyncio
async def test_list_materials_filters_inactive_by_default():
    """GET /api/materials (no params) → SELECT compiles to include
    materials.is_active = true. GET with include_inactive=true → no is_active
    filter in the WHERE."""
    db, stmts, _adds = _make_db()

    await list_materials(
        search=None, include_inactive=False, category=None, db=db, user=MagicMock()
    )
    default_sql = _compiled(stmts[-1])
    assert "materials.is_active = true" in default_sql, (
        f"Default list query must filter is_active=True. SQL: {default_sql}"
    )

    await list_materials(
        search=None, include_inactive=True, category=None, db=db, user=MagicMock()
    )
    opt_in_sql = _compiled(stmts[-1])
    assert "materials.is_active = true" not in opt_in_sql, (
        "include_inactive=True must drop the is_active filter. "
        f"SQL: {opt_in_sql}"
    )
    assert " where " not in opt_in_sql, (
        f"include_inactive=True with no search should have no WHERE clause. SQL: {opt_in_sql}"
    )


@pytest.mark.asyncio
async def test_list_movements_joins_orders_and_projects_order_code():
    """MAT-4-followup-2 — GET /api/materials/{id}/movements LEFT-JOINs orders so
    consumption rows can surface a human-readable order code (`#<external_id>`).
    Movements with no order_id still appear (outer join), with order_code=None."""
    material_id = uuid.uuid4()
    order_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    consumption_movement = MaterialMovement(
        material_id=material_id,
        delta=Decimal("-5.50"),
        reason=MaterialMovementReason.CONSUMPTION,
        order_id=order_id,
        unit_cost_at_movement=Decimal("588.0000"),
        user_id=uuid.uuid4(),
    )
    consumption_movement.id = uuid.uuid4()
    consumption_movement.created_at = now
    consumption_movement.receipt_id = None
    consumption_movement.notes = None

    receipt_movement = MaterialMovement(
        material_id=material_id,
        delta=Decimal("25"),
        reason=MaterialMovementReason.RECEIPT,
        order_id=None,
        unit_cost_at_movement=None,
        user_id=uuid.uuid4(),
    )
    receipt_movement.id = uuid.uuid4()
    receipt_movement.created_at = now
    receipt_movement.receipt_id = uuid.uuid4()
    receipt_movement.notes = None

    captured_stmts: list = []

    async def fake_execute(stmt):
        captured_stmts.append(stmt)
        r = MagicMock()
        r.all.return_value = [
            (consumption_movement, "7148183421084"),
            (receipt_movement, None),
        ]
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.get = AsyncMock(return_value=Material(name="x", unit="dm2", currency="UAH"))

    result = await list_material_movements(
        material_id=material_id,
        page=1,
        limit=20,
        reason=None,
        db=db,
        user=MagicMock(),
    )

    sql = _compiled(captured_stmts[-1])
    assert "join orders" in sql, (
        f"Movements query must LEFT JOIN orders to surface order_code. SQL: {sql}"
    )
    assert "orders.external_id" in sql

    assert len(result) == 2
    assert result[0].order_code == "#7148183421084"
    assert result[0].order_id == order_id
    assert result[1].order_code is None
    assert result[1].order_id is None


# ---------------------------------------------------------------------------
# WH-1 — category filter, new field defaults, and the paired-material guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_materials_filters_by_category_when_asked():
    """GET /api/materials?category=MATERIAL → the SELECT carries the filter.

    This is what keeps the backfilled packaging materials out of the BOM picker
    and the materials page; a client-side filter would leave the API open."""
    db, stmts, _adds = _make_db()

    await list_materials(
        search=None, include_inactive=False, category="MATERIAL", db=db,
        user=MagicMock(),
    )
    sql = _compiled(stmts[-1])
    assert "materials.category = 'material'" in sql, (
        f"category filter must reach SQL. SQL: {sql}"
    )


@pytest.mark.asyncio
async def test_list_materials_without_category_does_not_filter():
    """Unset means every category — the MCP tools and any other pre-WH-1 client
    must keep seeing exactly what they saw before."""
    db, stmts, _adds = _make_db()

    await list_materials(
        search=None, include_inactive=True, category=None, db=db, user=MagicMock()
    )
    sql = _compiled(stmts[-1])
    # The column is in the SELECT list either way; what must be absent is the
    # predicate (and with include_inactive=True there is no WHERE clause at all).
    assert "materials.category =" not in sql, (
        f"no category param must mean no category predicate. SQL: {sql}"
    )
    assert " where " not in sql, f"expected no WHERE clause at all. SQL: {sql}"


@pytest.mark.asyncio
async def test_create_material_defaults_to_tracked_material_category():
    """A payload that says nothing about WH-1's two fields must still produce
    today's material: MATERIAL, stock-tracked."""
    db, _stmts, adds = _make_db()
    body = MaterialCreate(name="Нитка вощена", unit="m", currency="UAH")

    await create_material(body=body, db=db, user=MagicMock())

    assert adds[0].category == "MATERIAL"
    assert adds[0].is_stock_tracked is True


@pytest.mark.asyncio
async def test_create_material_carries_wh1_fields_to_persistence():
    db, _stmts, adds = _make_db()
    body = MaterialCreate(
        name="Лазерна порізка",
        unit="pcs",
        currency="UAH",
        is_stock_tracked=False,
    )

    await create_material(body=body, db=db, user=MagicMock())

    assert adds[0].is_stock_tracked is False
    assert adds[0].category == "MATERIAL"


def _update_db(material: Material, *, paired: bool):
    """AsyncSession mock for update_material. `paired` decides whether the
    PackagingBox existence probe finds a row; every execute() is recorded so a
    test can assert the probe did NOT run."""
    captured_stmts: list = []

    async def fake_execute(stmt):
        captured_stmts.append(stmt)
        r = MagicMock()
        r.scalar = MagicMock(return_value=uuid.uuid4() if paired else None)
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.get = AsyncMock(return_value=material)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    return db, captured_stmts


def _material(**overrides) -> Material:
    fields = {
        "name": "100x120x50",
        "unit": "шт",
        "currency": "UAH",
        "current_unit_cost": Decimal("0"),
        "stock_quantity": Decimal("0"),
        "low_stock_threshold": Decimal("0"),
        "waste_percent": Decimal("0"),
        "is_active": True,
        "category": "PACKAGING",
        "is_stock_tracked": True,
    }
    fields.update(overrides)
    material = Material(**fields)
    material.id = uuid.uuid4()
    return material


@pytest.mark.asyncio
async def test_update_material_rejects_rename_of_a_paired_material():
    """WH-1 rule 6: the packaging page is the single place a box (and therefore
    its material) is named. Renaming from here would desync the pair with nothing
    to detect the drift — including for the MCP agent, which lands on this same
    endpoint."""
    from fastapi import HTTPException

    from schemas.material import MaterialUpdate

    material = _material()
    db, _stmts = _update_db(material, paired=True)

    with pytest.raises(HTTPException) as exc:
        await update_material(
            material_id=material.id,
            body=MaterialUpdate(name="Нова назва"),
            db=db,
            user=MagicMock(),
        )

    assert exc.value.status_code == 409
    assert "packaging" in exc.value.detail.lower()
    assert material.name == "100x120x50", "the rename must not have been applied"


@pytest.mark.asyncio
async def test_update_material_rejects_category_change_of_a_paired_material():
    from fastapi import HTTPException

    from schemas.material import MaterialUpdate

    material = _material()
    db, _stmts = _update_db(material, paired=True)

    with pytest.raises(HTTPException) as exc:
        await update_material(
            material_id=material.id,
            body=MaterialUpdate(category="MATERIAL"),
            db=db,
            user=MagicMock(),
        )

    assert exc.value.status_code == 409
    assert material.category == "PACKAGING"


@pytest.mark.asyncio
async def test_update_material_allows_an_unchanged_echo_on_a_paired_material():
    """A UI round-trip that PATCHes the current values back is a no-op, not a
    409 — the guard triggers on a real change."""
    from schemas.material import MaterialUpdate

    material = _material()
    db, stmts = _update_db(material, paired=True)

    await update_material(
        material_id=material.id,
        body=MaterialUpdate(name="100x120x50", category="PACKAGING", notes="ok"),
        db=db,
        user=MagicMock(),
    )

    assert material.notes == "ok"
    assert stmts == [], "no pairing probe when nothing guarded actually changed"


@pytest.mark.asyncio
async def test_update_material_allows_rename_when_not_paired():
    from schemas.material import MaterialUpdate

    material = _material(category="MATERIAL")
    db, _stmts = _update_db(material, paired=False)

    await update_material(
        material_id=material.id,
        body=MaterialUpdate(name="Шкіра нова"),
        db=db,
        user=MagicMock(),
    )

    assert material.name == "Шкіра нова"


@pytest.mark.asyncio
async def test_update_material_skips_the_pairing_probe_for_ordinary_fields():
    """The guard costs one query, and only when `name` or `category` is present.
    A plain is_stock_tracked flip must not pay for it."""
    from schemas.material import MaterialUpdate

    material = _material(category="MATERIAL")
    db, stmts = _update_db(material, paired=True)

    await update_material(
        material_id=material.id,
        body=MaterialUpdate(is_stock_tracked=False),
        db=db,
        user=MagicMock(),
    )

    assert stmts == []
    assert material.is_stock_tracked is False
