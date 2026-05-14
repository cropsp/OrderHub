"""MAT-1 — Materials router regression-guards.

Mirrors the compile-SQL pattern from test_finance_router.py / test_dashboard_router.py.
Captures SELECT statements via a mocked AsyncSession.execute and asserts on the
compiled SQL string. For the create path, captures `db.add(...)` to verify the
ORM instance carries the user-supplied `currency` value through to persistence.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from models.material import Material
from routers.materials import create_material, list_materials
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
