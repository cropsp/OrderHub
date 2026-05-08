"""BUG-6 — `ProductVariantRead` must accept zero-dimension rows.

IMP-1's CSV importer writes catalog rows with weight_g/length_mm/width_mm/
height_mm = 0 as a "fill me in" sentinel. Once CAT-VIS-1 opened the read-side
of /api/shops/{shop_id}/products to non-MANUAL shops, the response_model
re-validation crashed on those rows because ProductVariantBase enforced gt=0.

Fix: Base relaxes to ge=0 (so Read serializes), Create re-tightens to gt=0
(so manual product creation still requires real dimensions). Update keeps
gt=0 — once a user is typing a number, 0 is a typo, not a sentinel.
"""
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from schemas.product import (
    ProductVariantCreate,
    ProductVariantRead,
    ProductVariantUpdate,
)


DIMENSION_FIELDS = ["weight_g", "length_mm", "width_mm", "height_mm"]


def _read_payload(**overrides):
    base = {
        "id": uuid.uuid4(),
        "product_id": uuid.uuid4(),
        "sku": "TEST-SKU",
        "variant_name": "Test variant",
        "external_ref": None,
        "weight_g": 0,
        "length_mm": 0,
        "width_mm": 0,
        "height_mm": 0,
        "price": None,
        "cost_price": None,
        "stock_quantity": 0,
        "is_active": True,
        "volume_cm3": 0.0,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return base


def _create_payload(**overrides):
    base = {
        "sku": "TEST-SKU",
        "variant_name": "Test variant",
        "weight_g": 1,
        "length_mm": 1,
        "width_mm": 1,
        "height_mm": 1,
    }
    base.update(overrides)
    return base


def test_read_accepts_zero_dimensions():
    """Regression guard: IMP-1 sentinel rows must serialize via the Read schema."""
    variant = ProductVariantRead.model_validate(_read_payload())
    assert variant.weight_g == 0
    assert variant.length_mm == 0
    assert variant.width_mm == 0
    assert variant.height_mm == 0


def test_create_accepts_positive_dimensions():
    """Sanity check: Create still works with real dimensions."""
    variant = ProductVariantCreate.model_validate(_create_payload())
    assert variant.weight_g == 1


@pytest.mark.parametrize("field", DIMENSION_FIELDS)
def test_create_rejects_zero_dimension(field):
    """Manual product creation must require real dimensions — 0 is not allowed."""
    with pytest.raises(ValidationError):
        ProductVariantCreate.model_validate(_create_payload(**{field: 0}))


@pytest.mark.parametrize("field", DIMENSION_FIELDS)
def test_update_rejects_zero_dimension(field):
    """PATCH down to 0 is rejected — once typing a number, 0 is a typo."""
    with pytest.raises(ValidationError):
        ProductVariantUpdate.model_validate({field: 0})
