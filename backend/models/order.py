"""
OrderHub CRM — Order, OrderItem, OrderStatusHistory Models

Order: main business entity with shipping address, financial fields, and status workflow.
OrderItem: individual line items (Etsy CSV can have multiple rows per order).
OrderStatusHistory: immutable audit log of status changes.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OrderStatus(str, enum.Enum):
    NEW = "new"
    WAITING_INFO = "waiting_info"
    INFO_RECEIVED = "info_received"
    DESIGN_PENDING = "design_pending"
    DESIGN_READY = "design_ready"
    IN_PRODUCTION = "in_production"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ─── Status transition matrix ────────────────────────────────
# Maps each status to a set of allowed target statuses.
ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.NEW: {
        OrderStatus.WAITING_INFO,
        OrderStatus.INFO_RECEIVED,
        OrderStatus.DESIGN_PENDING,
        OrderStatus.IN_PRODUCTION,
        OrderStatus.CANCELLED,
    },
    OrderStatus.WAITING_INFO: {
        OrderStatus.INFO_RECEIVED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.INFO_RECEIVED: {
        OrderStatus.DESIGN_PENDING,
        OrderStatus.IN_PRODUCTION,
        OrderStatus.CANCELLED,
    },
    OrderStatus.DESIGN_PENDING: {
        OrderStatus.DESIGN_READY,
        OrderStatus.INFO_RECEIVED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.DESIGN_READY: {
        OrderStatus.IN_PRODUCTION,
        OrderStatus.DESIGN_PENDING,
        OrderStatus.CANCELLED,
    },
    OrderStatus.IN_PRODUCTION: {
        OrderStatus.SHIPPED,
        OrderStatus.DESIGN_PENDING,
        OrderStatus.CANCELLED,
    },
    OrderStatus.SHIPPED: {
        OrderStatus.COMPLETED,
        OrderStatus.IN_PRODUCTION,
    },
    OrderStatus.COMPLETED: set(),  # terminal
    OrderStatus.CANCELLED: {
        OrderStatus.NEW,  # reopen, owner only
    },
}


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("external_id", "shop_id", name="uq_order_external_shop"),
    )

    external_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", create_constraint=True),
        default=OrderStatus.NEW,
        nullable=False,
        index=True,
    )

    # Order summary
    title: Mapped[str] = mapped_column(Text, nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    # Financial (owner only)
    production_cost: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    # MAT-3 forward-compat: populated by MAT-4's consumption hook on SHIPPED.
    # No service-layer writes in MAT-3.
    computed_production_cost: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    shipping_np_cost: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    platform_fee: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Shipping address
    shipping_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shipping_street_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_street_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipping_state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipping_zip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shipping_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    shipping_city_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shipping_warehouse_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Designer assignment
    assigned_designer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # TTN (Nova Poshta tracking)
    ttn_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ttn_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ttn_printed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Computed parcel dimensions (Phase 4 calculation)
    computed_parcel_weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    computed_parcel_length_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    computed_parcel_width_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    computed_parcel_height_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    computed_packaging_box_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("packaging_boxes.id", ondelete="SET NULL"), nullable=True
    )
    parcel_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Operator-chosen packaging (PKG-1) — distinct from computed_packaging_box_id.
    packaging_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("packaging_boxes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Notes
    customer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    shop = relationship("Shop", back_populates="orders", lazy="selectin")
    customer = relationship("Customer", back_populates="orders", lazy="selectin")
    assigned_designer = relationship(
        "User", back_populates="assigned_orders", foreign_keys=[assigned_designer_id]
    )
    items = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    status_history = relationship(
        "OrderStatusHistory",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusHistory.changed_at",
        lazy="selectin",
    )
    attachments = relationship(
        "Attachment", back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    packaging = relationship(
        "PackagingBox", foreign_keys=[packaging_id], lazy="selectin"
    )

    @property
    def platform(self) -> str:
        """Derive platform from shop — never store separately."""
        return self.shop.platform.value if self.shop else "unknown"

    def __repr__(self) -> str:
        return f"<Order {self.external_id} [{self.status.value}]>"


class OrderItem(Base, UUIDPrimaryKeyMixin):
    """Individual line item within an order. Etsy CSV may have multiple rows per order."""

    __tablename__ = "order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    listing_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    variations: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Product Catalog Linking & Snapshot
    product_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True
    )
    snapshot_weight_g: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_length_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_width_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_height_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )

    @hybrid_property
    def volume_cm3(self) -> float:
        """Calculates volume in cm3 from snapshot dimensions."""
        length = self.snapshot_length_mm
        width = self.snapshot_width_mm
        height = self.snapshot_height_mm
        if length is None or width is None or height is None:
            return 0.0
        return (length * width * height) / 1000.0

    # Relationships
    order = relationship("Order", back_populates="items")
    variant = relationship("ProductVariant", back_populates="order_items")

    def __repr__(self) -> str:
        return f"<OrderItem {self.title} x{self.quantity}>"


class OrderStatusHistory(Base, UUIDPrimaryKeyMixin):
    """Immutable audit log of order status transitions."""

    __tablename__ = "order_status_history"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    changed_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"),
        nullable=False,
    )
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )

    # Relationships
    order = relationship("Order", back_populates="status_history")
    changed_by = relationship("User", back_populates="status_changes")

    def __repr__(self) -> str:
        return f"<StatusHistory {self.from_status} → {self.to_status}>"
