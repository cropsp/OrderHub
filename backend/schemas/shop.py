"""
OrderHub CRM — Shop Schemas
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from models.shop import ShopPlatform


class ShopBase(BaseModel):
    name: str = Field(..., max_length=255)
    platform: ShopPlatform
    shopify_store_url: HttpUrl | str | None = None
    np_sender_name: str | None = Field(None, max_length=255)
    np_sender_phone: str | None = Field(None, max_length=20)
    np_sender_city_ref: str | None = Field(None, max_length=36)
    np_sender_warehouse_ref: str | None = Field(None, max_length=36)
    np_default_description: str | None = Field(None, max_length=255)
    np_default_weight_kg: float = 0.5
    np_default_volume_m3: float = 0.004
    np_default_payer_type: str = Field("Sender", max_length=20)
    np_default_payment_method: str = Field("Cash", max_length=20)
    color: str = Field("#6366F1", max_length=7)
    is_active: bool = True


class ShopCreate(ShopBase):
    """Payload for creating a new shop (including raw tokens for encryption)."""
    shopify_access_token: str | None = None
    shopify_webhook_secret: str | None = None
    np_api_key: str | None = None


class ShopUpdate(BaseModel):
    """Payload for updating a shop (all fields optional)."""
    name: str | None = Field(None, max_length=255)
    shopify_store_url: HttpUrl | str | None = None
    shopify_access_token: str | None = None
    shopify_webhook_secret: str | None = None
    np_api_key: str | None = None
    np_sender_name: str | None = Field(None, max_length=255)
    np_sender_phone: str | None = Field(None, max_length=20)
    np_sender_city_ref: str | None = Field(None, max_length=36)
    np_sender_warehouse_ref: str | None = Field(None, max_length=36)
    np_default_description: str | None = Field(None, max_length=255)
    np_default_weight_kg: float | None = None
    np_default_volume_m3: float | None = None
    np_default_payer_type: str | None = Field(None, max_length=20)
    np_default_payment_method: str | None = Field(None, max_length=20)
    color: str | None = Field(None, max_length=7)
    is_active: bool | None = None


class ShopResponse(ShopBase):
    """Returned shop details with masked tokens."""
    id: uuid.UUID
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime
    
    # We return boolean flags instead of the tokens themselves, 
    # to let the frontend know if they are configured
    has_shopify_token: bool = False
    has_shopify_webhook_secret: bool = False
    has_np_token: bool = False

    model_config = ConfigDict(from_attributes=True)


class ShopDetailResponse(ShopResponse):
    """Shop details including computed metrics like order count."""
    order_count: int = 0
