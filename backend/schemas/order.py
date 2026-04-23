"""
OrderHub CRM — Order Schemas
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.order import OrderStatus


# ─── Order Items ───────────────────────────────────────────

class OrderItemResponse(BaseModel):
    id: uuid.UUID
    listing_id: str | None
    sku: str | None
    title: str
    quantity: int
    unit_price: float
    currency: str
    variations: str | None
    product_variant_id: uuid.UUID | None
    snapshot_weight_g: int | None
    snapshot_length_mm: int | None
    snapshot_width_mm: int | None
    snapshot_height_mm: int | None
    snapshot_title: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Status History ────────────────────────────────────────

class StatusHistoryResponse(BaseModel):
    id: uuid.UUID
    from_status: str
    to_status: str
    comment: str | None
    changed_at: datetime
    # We will compute a string representation of the user who changed it
    changed_by_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ─── Orders ───────────────────────────────────────────────

class OrderBase(BaseModel):
    external_id: str = Field(..., max_length=100)
    status: OrderStatus
    title: str
    total_price: float
    currency: str
    
    # Financial (owner only)
    production_cost: float | None = None
    shipping_np_cost: float | None = None
    platform_fee: float | None = None

    # Shipping
    shipping_name: str | None = None
    shipping_phone: str | None = None
    shipping_street_1: str | None = None
    shipping_street_2: str | None = None
    shipping_city: str | None = None
    shipping_state: str | None = None
    shipping_zip: str | None = None
    shipping_country: str | None = Field(None, max_length=2)
    shipping_city_ref: str | None = None
    shipping_warehouse_ref: str | None = None

    # Notes
    customer_note: str | None = None
    custom_info: str | None = None
    internal_note: str | None = None

    # Timestamps
    ordered_at: datetime
    shipped_at: datetime | None = None
    completed_at: datetime | None = None
    
    # TTN
    ttn_number: str | None = None
    ttn_created_at: datetime | None = None
    ttn_printed: bool = False


class OrderListResponse(OrderBase):
    """Lightweight order data for list views."""
    id: uuid.UUID
    shop_id: uuid.UUID
    customer_id: uuid.UUID
    assigned_designer_id: uuid.UUID | None
    assigned_at: datetime | None
    created_at: datetime
    updated_at: datetime
    
    # Derived fields
    shop_name: str | None = None
    customer_name: str | None = None
    platform: str | None = None

    model_config = ConfigDict(from_attributes=True)


class OrderResponse(OrderListResponse):
    """Full order data including nested relations."""
    items: list[OrderItemResponse] = []
    status_history: list[StatusHistoryResponse] = []


class OrderItemCreate(BaseModel):
    """Payload for manual order item creation."""
    title: str
    quantity: int = 1
    unit_price: float
    currency: str = "USD"
    variations: str | None = None
    product_variant_id: uuid.UUID | None = None



class OrderItemUpdate(BaseModel):
    """Payload for manual order item update."""
    title: str | None = None
    quantity: int | None = None
    unit_price: float | None = None
    currency: str | None = None
    variations: str | None = None
    product_variant_id: uuid.UUID | None = None


class OrderCreate(BaseModel):
    """Payload for manual order creation."""
    shop_id: uuid.UUID
    email: str  # We look up/create Customer by email
    full_name: str
    external_id: str
    title: str
    total_price: float
    currency: str = "USD"
    ordered_at: datetime
    
    # Items
    items: list[OrderItemCreate] = []

    # Shipping
    shipping_name: str | None = None
    shipping_phone: str | None = None
    shipping_street_1: str | None = None
    shipping_street_2: str | None = None
    shipping_city: str | None = None
    shipping_state: str | None = None
    shipping_zip: str | None = None
    shipping_country: str | None = None
    shipping_city_ref: str | None = None
    shipping_warehouse_ref: str | None = None


class OrderUpdate(BaseModel):
    """Payload for updating an order."""
    title: str | None = None
    # Financial fields (restricted by role in service)
    production_cost: float | None = None
    shipping_np_cost: float | None = None
    platform_fee: float | None = None
    
    # Assignment
    assigned_designer_id: uuid.UUID | None = None
    
    # Notes
    internal_note: str | None = None
    custom_info: str | None = None
    
    # TTN
    ttn_number: str | None = None
    ttn_printed: bool | None = None
    
    # Shipping
    shipping_name: str | None = None
    shipping_phone: str | None = None
    shipping_street_1: str | None = None
    shipping_street_2: str | None = None
    shipping_city: str | None = None
    shipping_state: str | None = None
    shipping_zip: str | None = None
    shipping_country: str | None = None
    shipping_city_ref: str | None = None
    shipping_warehouse_ref: str | None = None


class StatusChangeRequest(BaseModel):
    """Payload for transitioning order status."""
    new_status: OrderStatus
    comment: str | None = None
class OrderFilters(BaseModel):
    status: OrderStatus | None = None
    shop_id: uuid.UUID | None = None
    search: str | None = None
    assigned_designer_id: uuid.UUID | None = None
