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
async def test_list_materials_filters_inactive_by_default():
    """GET /api/materials (no params) → SELECT compiles to include
    materials.is_active = true. GET with include_inactive=true → no is_active
    filter in the WHERE."""
    db, stmts, _adds = _make_db()

    await list_materials(search=None, include_inactive=False, db=db, user=MagicMock())
    default_sql = _compiled(stmts[-1])
    assert "materials.is_active = true" in default_sql, (
        f"Default list query must filter is_active=True. SQL: {default_sql}"
    )

    await list_materials(search=None, include_inactive=True, db=db, user=MagicMock())
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
