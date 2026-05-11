"""
OrderHub CRM — Shop Model

Represents an Etsy or Shopify store with optional
Nova Poshta sender configuration and encrypted API tokens.
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ShopPlatform(str, enum.Enum):
    ETSY = "etsy"
    SHOPIFY = "shopify"
    MANUAL = "manual"


class Shop(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "shops"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[ShopPlatform] = mapped_column(
        Enum(ShopPlatform, name="shop_platform", create_constraint=True),
        nullable=False,
    )

    # Shopify-specific
    shopify_store_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    shopify_access_token_encrypted: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    shopify_webhook_secret_encrypted: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # Nova Poshta sender configuration (per shop)
    np_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    np_sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    np_sender_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    np_sender_city_ref: Mapped[str | None] = mapped_column(String(36), nullable=True)
    np_sender_warehouse_ref: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    np_sender_ref: Mapped[str | None] = mapped_column(String(36), nullable=True)
    np_sender_contact_ref: Mapped[str | None] = mapped_column(String(36), nullable=True)
    np_default_description: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    np_default_weight_kg: Mapped[float] = mapped_column(Float, default=0.5)
    np_default_volume_m3: Mapped[float] = mapped_column(Float, default=0.004)
    np_default_payer_type: Mapped[str] = mapped_column(String(20), default="Sender")
    np_default_payment_method: Mapped[str] = mapped_column(String(20), default="Cash")

    # UI
    color: Mapped[str] = mapped_column(String(7), default="#6366F1")

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    orders = relationship("Order", back_populates="shop", lazy="selectin")
    products = relationship("Product", back_populates="shop", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Shop {self.name} ({self.platform.value})>"
