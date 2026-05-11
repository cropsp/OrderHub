import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from services.parcel_calculator import calculate_parcel_estimate
from models.packaging import PackagingType
from schemas.packaging import PackagingBoxRead

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
    
    mock_order_result = MagicMock()
    mock_order_result.scalar_one_or_none.return_value = order
    mock_pkg_result = MagicMock()
    mock_pkg_result.scalars.return_value.all.return_value = [env, box]
    db.execute.side_effect = [mock_order_result, mock_pkg_result]
    
    estimate = await calculate_parcel_estimate(db, str(order_id))
    
    assert estimate.selected_packaging.name == "Standard Box"
    assert estimate.total_weight_g == 1100
    assert estimate.packaging_type == "BOX"
