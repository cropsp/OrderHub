"""
OrderHub CRM — Product and ProductVariant Models
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Main product entity. Scoped to a shop.
    Supports future Etsy/Shopify mapping via external_ref.
    """
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("shop_id", "external_ref", name="uq_product_shop_external"),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # RESERVED for etsy_listing_id / shopify_product_id
    external_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    shop = relationship("Shop", back_populates="products")
    variants: Mapped[List["ProductVariant"]] = relationship(
        "ProductVariant", back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Product {self.title} (Shop: {self.shop_id})>"


class ProductVariant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Specific variant of a product (e.g. Size M, Color Red).
    Contains physical dimensions for parcel calculation.
    """
    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "sku", name="uq_variant_product_sku"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    sku: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    variant_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # RESERVED for etsy_product_id / shopify_variant_id
    external_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Physical dimensions (Base units: grams and millimeters)
    weight_g: Mapped[int] = mapped_column(Integer, nullable=False)
    length_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    width_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    height_mm: Mapped[int] = mapped_column(Integer, nullable=False)

    # Pricing & stock
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    cost_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    product = relationship("Product", back_populates="variants")
    order_items = relationship("OrderItem", back_populates="variant")

    @hybrid_property
    def volume_cm3(self) -> float:
        """
        Calculates volume in cm3 (L * W * H / 1,000,000).
        Stored as mm, so divide by 1,000,000 to get cm3.
        """
        return (self.length_mm * self.width_mm * self.height_mm) / 1000.0

    def __repr__(self) -> str:
        return f"<ProductVariant SKU:{self.sku} Weight:{self.weight_g}g>"
