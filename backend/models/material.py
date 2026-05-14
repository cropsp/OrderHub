"""
OrderHub CRM — Materials Models

MAT-1: Catalog entities (Material, OverheadMaterial).
MAT-2: Live stock + audit ledger (MaterialReceipt, OverheadMaterialReceipt,
       MaterialMovement). Weighted-average cost recompute fires on every
       MaterialReceipt via material_stock_service.apply_receipt.

Two parallel direct/indirect entities per the design doc settled-decision #1:
  - Material: direct materials (bind to BOMs in MAT-3, decrement on shipment in MAT-4)
  - OverheadMaterial: indirect/consumables (tracked as flat expenses, never decrement)
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MaterialMovementReason(str, enum.Enum):
    """All four values ship in MAT-2 (rule #9 from task.md). Only RECEIPT and
    ADJUSTMENT/WASTE are emitted by code paths in MAT-2 — CONSUMPTION is reserved
    for MAT-4 but lands now so the ENUM is forward-compatible without ALTER TYPE.
    """

    RECEIPT = "receipt"
    CONSUMPTION = "consumption"
    WASTE = "waste"
    ADJUSTMENT = "adjustment"


class Material(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "materials"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    current_unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0")
    )
    stock_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    low_stock_threshold: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    waste_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    supplier_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    receipts = relationship(
        "MaterialReceipt",
        back_populates="material",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MaterialReceipt.received_at.desc()",
    )
    # lazy='dynamic' — ledger grows unboundedly; matches PackagingBox.stock_movements.
    movements = relationship(
        "MaterialMovement",
        back_populates="material",
        lazy="dynamic",
        order_by="MaterialMovement.created_at.desc()",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (Index("ix_materials_is_active_name", "is_active", "name"),)

    def __repr__(self) -> str:
        return f"<Material {self.name} ({self.unit}, {self.currency})>"


class OverheadMaterial(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "overhead_materials"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    receipts = relationship(
        "OverheadMaterialReceipt",
        back_populates="overhead_material",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="OverheadMaterialReceipt.received_at.desc()",
    )

    __table_args__ = (
        Index("ix_overhead_materials_is_active_name", "is_active", "name"),
    )

    def __repr__(self) -> str:
        return f"<OverheadMaterial {self.name} ({self.unit})>"


class MaterialReceipt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "material_receipts"

    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    shipping_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    is_initial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supplier: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    invoice_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    material = relationship("Material", back_populates="receipts")

    def __repr__(self) -> str:
        return (
            f"<MaterialReceipt material={self.material_id} qty={self.qty} "
            f"unit_cost={self.unit_cost}>"
        )


class OverheadMaterialReceipt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "overhead_material_receipts"

    overhead_material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("overhead_materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional per-shop tagging. NULL → unallocated; surfaces on a global card
    # in MAT-5. Settled-decision #11.
    shop_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shops.id", ondelete="SET NULL"),
        nullable=True,
    )
    qty: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    supplier: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    invoice_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    overhead_material = relationship("OverheadMaterial", back_populates="receipts")

    __table_args__ = (
        Index(
            "ix_overhead_material_receipts_shop_id_received_at",
            "shop_id",
            "received_at",
            postgresql_where=text("shop_id IS NOT NULL"),
        ),
        Index("ix_overhead_material_receipts_received_at", "received_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<OverheadMaterialReceipt material={self.overhead_material_id} "
            f"total={self.total_cost} {self.currency}>"
        )


class MaterialMovement(Base, UUIDPrimaryKeyMixin):
    """Append-only audit ledger for every Material stock change.

    Mirrors PKG-2's PackagingStockMovement. `stock_quantity` on Material is the
    running sum of `delta`; both are updated transactionally by
    material_stock_service.apply_movement.

    CHECK constraint enforces cost-snapshot integrity for future MAT-4
    consumption rows: `unit_cost_at_movement` is required iff reason='consumption'.
    """

    __tablename__ = "material_movements"

    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    delta: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[MaterialMovementReason] = mapped_column(
        Enum(
            MaterialMovementReason,
            name="material_movement_reason",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            create_constraint=True,
        ),
        nullable=False,
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    receipt_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("material_receipts.id", ondelete="SET NULL"),
        nullable=True,
    )
    unit_cost_at_movement: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    material = relationship("Material", back_populates="movements")
    receipt = relationship("MaterialReceipt")

    __table_args__ = (
        CheckConstraint(
            "(reason = 'consumption' AND unit_cost_at_movement IS NOT NULL) OR "
            "(reason != 'consumption' AND unit_cost_at_movement IS NULL)",
            name="ck_material_movement_consumption_cost",
        ),
        Index(
            "ix_material_movements_order_id",
            "order_id",
            postgresql_where=text("order_id IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MaterialMovement material={self.material_id} delta={self.delta:+} "
            f"reason={self.reason.value}>"
        )
