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

    # WH-2: this table's own stock_quantity / low_stock_threshold columns are GONE.
    # A box is counted exactly once, on its material, so there is no second counter
    # to drift. Left default-lazy on purpose: Order.packaging is mapper-level
    # lazy="selectin", so making this eager would add a materials query to every
    # page of GET /api/orders — which never reads the object. The three call sites
    # that build PackagingBoxRead load it explicitly (catalog_service,
    # parcel_calculator).
    material = relationship("Material", lazy="select")

    @property
    def stock_quantity(self):
        """On-hand units, read through the paired material.

        Kept under the old column's name so PackagingBoxRead, the frontend type and
        every existing caller keep working — only the storage moved. Reading this on
        a box whose material was not eagerly loaded raises MissingGreenlet in async
        context, which is the intended loud failure: a box read without its material
        cannot answer this question, and guessing zero would be a lie.
        """
        return self.material.stock_quantity

    @property
    def low_stock_threshold(self):
        """Restock trigger, read through the paired material. See stock_quantity."""
        return self.material.low_stock_threshold

    @property
    def material_is_active(self) -> bool:
        """Whether the box is still in the catalogue. Archiving a box deactivates
        its material — the box has no is_active of its own to fall out of sync."""
        return self.material.is_active

    # lazy='dynamic' deviates from the selectin default. Ledger grows unbounded
    # (one row per TTN op forever); eagerly loading on GET /packaging-boxes would
    # degrade the list endpoint.
    #
    # WH-2 FROZE this ledger: nothing in the application writes to it any more (the
    # TTN hooks and the restock endpoint that fed it are gone) and nothing reads it.
    # Table and rows stay as archaeology, which is also why archiving a box no
    # longer deletes the row that would CASCADE them away.
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
