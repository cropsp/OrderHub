"""WH-1 — a packaging box and its Material live and die together.

CatalogService now mints a PACKAGING Material alongside every box, keeps its name
in step, and archives it instead of orphaning it on delete. These guards use a
mocked AsyncSession in the style of test_materials_router.py; the FK, the UNIQUE
constraint and the backfill are the migration's job and are verified by the
up/down/up round trip, not here.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.material import Material
from models.packaging import PackagingBox
from schemas.packaging import PackagingBoxCreate, PackagingBoxUpdate
from services.catalog_service import (
    PACKAGING_MATERIAL_CURRENCY,
    PACKAGING_MATERIAL_UNIT,
    CatalogService,
)


def _make_db(*, box: PackagingBox | None = None, material: Material | None = None):
    """AsyncSession mock capturing add()ed instances and delete() statements.

    `flush` assigns the ids SQLAlchemy would assign at INSERT, because the paired
    create reads `material.id` to point the geometry row at it.
    """
    adds: list = []
    executed: list = []

    async def fake_execute(stmt):
        executed.append(stmt)
        r = MagicMock()
        # WH-2: create/update end with a re-fetch (the row has to come back with its
        # material loaded, which db.refresh cannot do). With no explicit `box`, hand
        # back whatever was just staged, the way the real SELECT would.
        staged = next((o for o in reversed(adds) if isinstance(o, PackagingBox)), None)
        r.scalar_one_or_none = MagicMock(
            return_value=box if box is not None else staged
        )
        return r

    async def fake_flush():
        for obj in adds:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    db = MagicMock()
    db.execute = AsyncMock(side_effect=fake_execute)
    db.get = AsyncMock(return_value=material)
    db.add = MagicMock(side_effect=lambda obj: adds.append(obj))
    db.flush = AsyncMock(side_effect=fake_flush)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db, adds, executed


def _create_schema(**overrides) -> PackagingBoxCreate:
    fields = {
        "name": "100x120x50",
        "inner_length_mm": 100,
        "inner_width_mm": 120,
        "inner_height_mm": 50,
        "max_weight_g": 2000,
    }
    fields.update(overrides)
    return PackagingBoxCreate(**fields)


@pytest.mark.asyncio
async def test_create_packaging_box_mints_the_paired_material():
    """Every rule-4 value, pinned. A box entered here must be indistinguishable
    from one the migration backfilled, or the two entry paths diverge silently."""
    db, adds, _ = _make_db()

    box = await CatalogService(db).create_packaging_box(_create_schema())

    materials = [o for o in adds if isinstance(o, Material)]
    boxes = [o for o in adds if isinstance(o, PackagingBox)]
    assert len(materials) == 1 and len(boxes) == 1

    material = materials[0]
    assert material.name == "100x120x50"
    assert material.unit == PACKAGING_MATERIAL_UNIT
    assert material.currency == PACKAGING_MATERIAL_CURRENCY
    assert material.category == "PACKAGING"
    assert material.is_stock_tracked is True
    assert material.is_active is True
    assert material.supplier_sku is None
    assert box.material_id == material.id


@pytest.mark.asyncio
async def test_create_packaging_box_commits_once():
    """Both rows land in ONE transaction — a box must never exist without its
    material, and vice versa."""
    db, _adds, _ = _make_db()

    await CatalogService(db).create_packaging_box(_create_schema())

    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_create_packaging_box_takes_no_author():
    """WH-1 kept a user_id parameter alive for the initial_stock ledger row. WH-2
    deleted that row's only producer, so the parameter went with it — nothing in a
    paired create is authored, and the CSV-confirm path (which has no user) is
    exactly as valid as the interactive one."""
    import inspect

    params = inspect.signature(CatalogService.create_packaging_box).parameters
    assert "user_id" not in params

    db, adds, _ = _make_db()
    await CatalogService(db).create_packaging_box(_create_schema())
    assert any(isinstance(o, Material) for o in adds)


@pytest.mark.asyncio
async def test_create_writes_the_threshold_onto_the_material():
    """WH-2: the box row has no low_stock_threshold column any more. The packaging
    form still collects it — it is the surface where boxes are managed — and it has
    to land on the material or the dashboard card silently reads a default of 0."""
    db, adds, _ = _make_db()

    await CatalogService(db).create_packaging_box(
        _create_schema(low_stock_threshold=12)
    )

    material = next(o for o in adds if isinstance(o, Material))
    assert material.low_stock_threshold == 12
    box = next(o for o in adds if isinstance(o, PackagingBox))
    assert not hasattr(type(box), "__table__") or (
        "low_stock_threshold" not in type(box).__table__.columns
    ), "the counter must not have a second home on the box row"


@pytest.mark.asyncio
async def test_threshold_update_is_routed_to_the_material():
    material = Material(
        name="box", unit="шт", currency="UAH", category="PACKAGING",
        low_stock_threshold=Decimal("5"),
    )
    material.id = uuid.uuid4()
    box = PackagingBox(name="box", material_id=material.id)
    box.id = uuid.uuid4()
    db, _adds, _ = _make_db(box=box, material=material)

    await CatalogService(db).update_packaging_box(
        box.id, PackagingBoxUpdate(low_stock_threshold=Decimal("20"))
    )

    assert material.low_stock_threshold == Decimal("20")


@pytest.mark.asyncio
async def test_rename_syncs_the_paired_material():
    material = Material(name="old", unit="шт", currency="UAH", category="PACKAGING")
    material.id = uuid.uuid4()
    box = PackagingBox(name="old", material_id=material.id)
    box.id = uuid.uuid4()
    db, _adds, _ = _make_db(box=box, material=material)

    await CatalogService(db).update_packaging_box(
        box.id, PackagingBoxUpdate(name="Конверт A5")
    )

    assert box.name == "Конверт A5"
    assert material.name == "Конверт A5", "the material must follow the box"


@pytest.mark.asyncio
async def test_update_without_a_name_never_loads_the_material():
    material = Material(name="old", unit="шт", currency="UAH", category="PACKAGING")
    material.id = uuid.uuid4()
    box = PackagingBox(name="old", material_id=material.id, sort_order=0)
    box.id = uuid.uuid4()
    db, _adds, _ = _make_db(box=box, material=material)

    await CatalogService(db).update_packaging_box(
        box.id, PackagingBoxUpdate(sort_order=3)
    )

    assert box.sort_order == 3
    assert db.get.await_count == 0


@pytest.mark.asyncio
async def test_archive_deactivates_the_material_and_keeps_the_geometry_row():
    """WH-2 finishes WH-1's half-measure. The geometry row used to be hard-deleted,
    which CASCADE-ed packaging_stock_movements — the very rows WH-2 freezes as
    read-only history — and left the material pointing at nothing. Now nothing is
    destroyed: the box simply stops being active."""
    material = Material(
        name="100x120x50", unit="шт", currency="UAH", category="PACKAGING",
        is_active=True,
    )
    material.id = uuid.uuid4()
    box = PackagingBox(name="100x120x50", material_id=material.id)
    box.id = uuid.uuid4()
    db, _adds, executed = _make_db(box=box, material=material)

    await CatalogService(db).archive_packaging_box(box.id)

    assert material.is_active is False
    assert not any("DELETE" in str(stmt).upper() for stmt in executed), (
        "the geometry row and its frozen ledger must survive"
    )
    assert db.commit.await_count == 1


@pytest.mark.asyncio
async def test_archive_of_a_missing_box_is_a_no_op():
    """Preserves today's silent 204 on an unknown id — no write, no commit."""
    db, _adds, executed = _make_db(box=None)

    await CatalogService(db).archive_packaging_box(uuid.uuid4())

    assert db.commit.await_count == 0
