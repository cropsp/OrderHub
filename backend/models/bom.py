"""
OrderHub CRM — Bill of Materials Model

MAT-3: BomItem entity — one row per (Product, Material) pair. Multiple rows per
Product compose a recipe. BOM lives at Product level (NOT ProductVariant) per
design doc settled-decision #7.

Consumption logic (decrement on SHIPPED) is reserved for MAT-4. MAT-3 only
authors recipes and computes a theoretical unit cost preview.
"""

import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BomItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "bom_items"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Materials are never hard-deleted (soft-delete via is_active=False).
    # RESTRICT defends against accidental hard delete leaving orphan BomItems.
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("materials.id", ondelete="RESTRICT"),
        nullable=False,
    )
    qty_per_unit: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    material = relationship("Material", lazy="joined")

    __table_args__ = (
        UniqueConstraint(
            "product_id", "material_id", name="uq_bom_items_product_material"
        ),
        CheckConstraint("qty_per_unit > 0", name="ck_bom_items_qty_positive"),
    )

    def __repr__(self) -> str:
        return (
            f"<BomItem product={self.product_id} material={self.material_id} "
            f"qty={self.qty_per_unit}>"
        )
