"""ADDR-VAL-2 — OrderResponse must expose the persisted address-validation fields.

ADDR-VAL-1 persists `address_validation_status` / `address_validation_at` on the order,
but the GET /orders/{id} response (OrderResponse) did not serialize them, so the
order-detail badge had nothing to render on load. These assert the from_attributes
round-trip carries both through.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from models.order import AddressValidationStatus, OrderStatus
from schemas.order import OrderResponse


def _order_row(**overrides):
    """A minimal ORM-like object with every no-default OrderResponse field set."""
    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)
    row = dict(
        external_id="EXT-1",
        status=OrderStatus.NEW,
        title="Test Order",
        total_price=100.0,
        currency="USD",
        ordered_at=now,
        id=uuid.uuid4(),
        shop_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        assigned_designer_id=None,
        assigned_at=None,
        created_at=now,
        updated_at=now,
        address_validation_status=AddressValidationStatus.NEEDS_ATTENTION,
        address_validation_at=now,
    )
    row.update(overrides)
    return SimpleNamespace(**row)


def test_order_response_serializes_address_validation_fields():
    resp = OrderResponse.model_validate(_order_row())
    dumped = resp.model_dump()
    assert dumped["address_validation_status"] is AddressValidationStatus.NEEDS_ATTENTION
    assert dumped["address_validation_at"] is not None


def test_order_response_address_validation_defaults_to_none():
    """A never-validated order (both columns NULL) serializes as None, not an error."""
    resp = OrderResponse.model_validate(
        _order_row(address_validation_status=None, address_validation_at=None)
    )
    assert resp.address_validation_status is None
    assert resp.address_validation_at is None
