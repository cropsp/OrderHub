"""
OrderHub CRM — Materials Models

MAT-1: Catalog entities only. No stock, no receipts, no BOM yet.
Two parallel entities per the design doc settled-decision #1:
  - Material: direct materials (bind to BOMs in MAT-3, decrement on shipment in MAT-4)
  - OverheadMaterial: indirect/consumables (tracked as flat expenses, never decrement)
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Material(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "materials"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    # ISO 4217. Locked at creation per design doc settled-decision #12.
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

    __table_args__ = (Index("ix_materials_is_active_name", "is_active", "name"),)

    def __repr__(self) -> str:
        return f"<Material {self.name} ({self.unit}, {self.currency})>"


class OverheadMaterial(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "overhead_materials"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_overhead_materials_is_active_name", "is_active", "name"),
    )

    def __repr__(self) -> str:
        return f"<OverheadMaterial {self.name} ({self.unit})>"
