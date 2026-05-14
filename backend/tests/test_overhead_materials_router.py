"""MAT-1 — Overhead materials router regression-guards.

Single-case smoke matching the materials list-filter pattern.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from routers.overhead_materials import list_overhead_materials


def _make_db():
    captured_stmts: list = []

    async def fake_execute(stmt):
        captured_stmts.append(stmt)
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        return r

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    return db, captured_stmts


def _compiled(stmt) -> str:
    return str(
        stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()


@pytest.mark.asyncio
async def test_list_overhead_materials_filters_inactive_by_default():
    db, stmts = _make_db()

    await list_overhead_materials(
        search=None, include_inactive=False, db=db, user=MagicMock()
    )
    default_sql = _compiled(stmts[-1])
    assert "overhead_materials.is_active = true" in default_sql, (
        f"Default list query must filter is_active=True. SQL: {default_sql}"
    )

    await list_overhead_materials(
        search=None, include_inactive=True, db=db, user=MagicMock()
    )
    opt_in_sql = _compiled(stmts[-1])
    assert "overhead_materials.is_active = true" not in opt_in_sql, (
        f"include_inactive=True must drop is_active filter. SQL: {opt_in_sql}"
    )
    assert " where " not in opt_in_sql, (
        f"include_inactive=True with no search should have no WHERE clause. SQL: {opt_in_sql}"
    )
