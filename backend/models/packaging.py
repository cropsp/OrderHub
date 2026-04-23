"""
OrderHub CRM — Packaging Models
"""

import enum
import uuid
from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PackagingType(str, enum.Enum):
    BOX = "BOX"
    ENVELOPE = "ENVELOPE"


class PackagingBox(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Available packaging inventory for a shop.
    Used by the parcel calculator to select the best fit.
    """
    __tablename__ = "packaging_boxes"

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
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

    # Relationships
    shop = relationship("Shop", back_populates="packaging_boxes")

    def __repr__(self) -> str:
        return f"<PackagingBox {self.name} ({self.packaging_type.value})>"
