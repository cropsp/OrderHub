import pytest
from decimal import Decimal
from uuid import uuid4
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from services.parcel_calculator import calculate_parcel_estimate
from models.packaging import PackagingType
from schemas.packaging import PackagingBoxRead


def _pair_with_material(box, *, stock=Decimal("40"), threshold=Decimal("5")):
    """WH-2: a box's counters are properties over its paired Material, and
    PackagingBoxRead reads them plus material_is_active. Setting them on the mock
    directly is enough — the property is shadowed by the attribute — but the
    material_id link is kept so the fixture still resembles the real row."""
    box.material_id = uuid4()
    box.stock_quantity = stock
    box.low_stock_threshold = threshold
    box.material_is_active = True
    return box


@pytest.mark.asyncio
async def test_calculate_parcel_estimate_basic():
    # Mock DB session
    db = AsyncMock()
    
    # Mock Order
    order_id = uuid4()
    shop_id = uuid4()
    order = MagicMock()
    order.id = order_id
    order.shop_id = shop_id
    
    # Mock Items
    item1 = MagicMock()
    item1.snapshot_weight_g = 100
    item1.snapshot_length_mm = 100
    item1.snapshot_width_mm = 50
    item1.snapshot_height_mm = 20
    item1.quantity = 2
    item1.volume_cm3 = 100.0
    
    order.items = [item1]
    
    mock_order_result = MagicMock()
    mock_order_result.scalar_one_or_none.return_value = order
    mock_pkg_result = MagicMock()
    mock_pkg_result.scalars.return_value.all.return_value = []
    db.execute.side_effect = [mock_order_result, mock_pkg_result]
    
    estimate = await calculate_parcel_estimate(db, str(order_id))
    
    assert estimate.total_weight_g == 200
    assert estimate.parcel_length_mm == 100
    assert estimate.parcel_width_mm == 50
    assert estimate.parcel_height_mm == 40
    assert "No packaging configured" in estimate.warnings[0]

@pytest.mark.asyncio
async def test_envelope_selection():
    db = AsyncMock()
    order_id = uuid4()
    shop_id = uuid4()
    order = MagicMock()
    order.id = order_id
    order.shop_id = shop_id
    
    item = MagicMock()
    item.snapshot_weight_g = 100
    item.snapshot_length_mm = 100
    item.snapshot_width_mm = 50
    item.snapshot_height_mm = 10
    item.quantity = 1
    item.volume_cm3 = 50.0
    order.items = [item]
    
    now = datetime.now()
    # Mock packaging - using real values for Pydantic validation
    env = MagicMock()
    env.id = uuid4()
    env.material_id = uuid4()  # WH-1: every box is backed by a Material
    env.name = "Small Envelope"
    env.packaging_type = PackagingType.ENVELOPE
    env.max_weight_g = 500
    env.max_thickness_mm = 20
    env.inner_length_mm = 150
    env.inner_width_mm = 100
    env.inner_height_mm = 20
    env.tare_weight_g = 5
    env.sort_order = 1
    env.created_at = now
    env.updated_at = now
    _pair_with_material(env)

    mock_order_result = MagicMock()
    mock_order_result.scalar_one_or_none.return_value = order
    mock_pkg_result = MagicMock()
    mock_pkg_result.scalars.return_value.all.return_value = [env]
    db.execute.side_effect = [mock_order_result, mock_pkg_result]
    
    estimate = await calculate_parcel_estimate(db, str(order_id))
    
    assert estimate.selected_packaging.name == "Small Envelope"
    assert estimate.total_weight_g == 105
    assert estimate.packaging_type == "ENVELOPE"

@pytest.mark.asyncio
async def test_box_fallback():
    db = AsyncMock()
    order_id = uuid4()
    shop_id = uuid4()
    order = MagicMock()
    order.id = order_id
    order.shop_id = shop_id
    
    item = MagicMock()
    item.snapshot_weight_g = 1000
    item.snapshot_length_mm = 100
    item.snapshot_width_mm = 100
    item.snapshot_height_mm = 100
    item.quantity = 1
    item.volume_cm3 = 1000.0
    order.items = [item]
    
    now = datetime.now()
    # Envelope (too small weight)
    env = MagicMock()
    env.packaging_type = PackagingType.ENVELOPE
    env.max_weight_g = 500
    env.max_thickness_mm = 0 # Not None to avoid TypeError in comparison if needed
    env.sort_order = 1
    
    # Box
    box = MagicMock()
    box.id = uuid4()
    box.material_id = uuid4()  # WH-1: every box is backed by a Material
    box.name = "Standard Box"
    box.packaging_type = PackagingType.BOX
    box.max_weight_g = 5000
    box.max_thickness_mm = None
    box.inner_length_mm = 200
    box.inner_width_mm = 200
    box.inner_height_mm = 200
    box.tare_weight_g = 100
    box.sort_order = 0
    box.created_at = now
    box.updated_at = now
    _pair_with_material(box)

    mock_order_result = MagicMock()
    mock_order_result.scalar_one_or_none.return_value = order
    mock_pkg_result = MagicMock()
    mock_pkg_result.scalars.return_value.all.return_value = [env, box]
    db.execute.side_effect = [mock_order_result, mock_pkg_result]
    
    estimate = await calculate_parcel_estimate(db, str(order_id))
    
    assert estimate.selected_packaging.name == "Standard Box"
    assert estimate.total_weight_g == 1100
    assert estimate.packaging_type == "BOX"


@pytest.mark.asyncio
async def test_archived_boxes_are_excluded_from_selection():
    """WH-2: the query filters on the paired Material's is_active, so an archived
    box can never be auto-suggested. Asserted on the compiled SQL because the
    filtering happens in the database, not in the Python selection loop — the
    fixture below would otherwise have to fake the DB's own job.
    """
    db = AsyncMock()
    order_id = uuid4()
    order = MagicMock()
    order.id = order_id
    order.items = []

    mock_order_result = MagicMock()
    mock_order_result.scalar_one_or_none.return_value = order
    mock_pkg_result = MagicMock()
    mock_pkg_result.scalars.return_value.all.return_value = []
    db.execute.side_effect = [mock_order_result, mock_pkg_result]

    await calculate_parcel_estimate(db, str(order_id))

    pkg_stmt = db.execute.await_args_list[1].args[0]
    sql = str(pkg_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "JOIN materials" in sql, "the paired material must be joined"

    # Only the WHERE clause counts here: stock_quantity appears in the SELECT list
    # because the material is eagerly loaded, which is exactly what we want — it is
    # a filter on it that we do not.
    where = sql.split("WHERE")[-1]
    assert "materials.is_active" in where, "archived boxes must be filtered out"
    # Stock is deliberately NOT a filter (design §10.5) — the calculator answers
    # "what fits", and hiding an empty box would leave the operator with no
    # suggestion and no reason why.
    assert "stock_quantity" not in where


@pytest.mark.asyncio
async def test_packaging_is_fetched_in_a_single_round_trip():
    """contains_eager over the join the filter already needs — not a second query.
    The two-element execute harness above is what would break first if this
    regressed, so state the requirement outright."""
    db = AsyncMock()
    order_id = uuid4()
    order = MagicMock()
    order.id = order_id
    order.items = []

    mock_order_result = MagicMock()
    mock_order_result.scalar_one_or_none.return_value = order
    mock_pkg_result = MagicMock()
    mock_pkg_result.scalars.return_value.all.return_value = []
    db.execute.side_effect = [mock_order_result, mock_pkg_result]

    await calculate_parcel_estimate(db, str(order_id))

    assert db.execute.await_count == 2
