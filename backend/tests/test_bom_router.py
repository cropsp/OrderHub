"""MAT-3 — BOM router / service regression-guards.

Mirrors the compile-SQL pattern from test_materials_router.py. Captures
DELETE / SELECT statements via a mocked AsyncSession.execute and asserts on
the compiled SQL string. Behavioral tests construct Pydantic payloads or
mock the joined Material relationship to drive the read projection.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
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
async def test_compute_bom_cost_groups_by_currency():
    """compute_bom_cost SELECT joins materials and groups by
    materials.currency, with a SUM over qty_per_unit * current_unit_cost."""
    db, stmts, _adds = _make_db()
    await bom_service.compute_bom_cost(db, product_id=uuid.uuid4())

    assert len(stmts) == 1, f"expected exactly 1 statement, got {len(stmts)}"
    sql = _compiled(stmts[0])
    assert "join materials" in sql, f"must JOIN materials. SQL: {sql}"
    assert "current_unit_cost" in sql, (
        f"must reference materials.current_unit_cost. SQL: {sql}"
    )
    assert "group by materials.currency" in sql, (
        f"must GROUP BY materials.currency. SQL: {sql}"
    )
    assert "sum(" in sql, f"must aggregate via SUM. SQL: {sql}"


def test_project_bom_item_flags_inactive_material():
    """A BomItem whose joined Material has is_active=False is projected with
    material_is_active=False — the editor uses this to render the amber
    Discontinued badge + recipe-level warning banner."""
    inactive_mat = MagicMock(
        name="Фанера 4mm",
        unit="m2",
        currency="UAH",
        current_unit_cost=Decimal("0"),
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
