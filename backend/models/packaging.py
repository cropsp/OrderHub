"""
OrderHub CRM — Packaging Models
"""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PackagingType(str, enum.Enum):
    BOX = "BOX"
    ENVELOPE = "ENVELOPE"


class PackagingBox(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Shared packaging inventory used by the parcel calculator to pick the
    best fit. As of PKG-1b, packaging is global (no shop scope).
    """
    __tablename__ = "packaging_boxes"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # WH-1: every box is backed 1:1 by a Material carrying its cost, receipts and
    # supplier article; this table keeps only the geometry the parcel calculator
    # needs. RESTRICT so archiving a material can never orphan the geometry row —
    # deleting a box archives its material instead (catalog_service).
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("materials.id", ondelete="RESTRICT", name="fk_packaging_boxes_material_id"),
        nullable=False,
    )
    packaging_type: Mapped[PackagingType] = mapped_column(
        Enum(PackagingType, name="packaging_type", create_constraint=True),
        default=PackagingType.BOX,
        nullable=False,
        index=True
    )
    
    # Internal Dimensions (mm)
    inner_length_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    inner_width_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    inner_height_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # ENVELOPE only: max sum of item heights; NULL = weight-only check
    max_thickness_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    max_weight_g: Mapped[int] = mapped_column(Integer, nullable=False)
    tare_weight_g: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # PKG-2: cached running sum of all packaging_stock_movements.delta for this box.
    # Always read by UI in O(1); mutated transactionally with every ledger INSERT.
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # lazy='dynamic' deviates from the selectin default. Ledger grows unbounded
    # (one row per TTN op forever); eagerly loading on GET /packaging-boxes would
    # degrade the list endpoint. Query explicitly when a history view is added.
    stock_movements = relationship(
        "PackagingStockMovement",
        backref="box",
        lazy="dynamic",
        order_by="PackagingStockMovement.created_at.desc()",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Named explicitly: an auto-named constraint from `unique=True` on the column
    # would not match the migration and would show up as autogenerate drift.
    __table_args__ = (
        UniqueConstraint("material_id", name="uq_packaging_boxes_material_id"),
    )

    def __repr__(self) -> str:
        return f"<PackagingBox {self.name} ({self.packaging_type.value})>"
