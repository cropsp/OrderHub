"""
OrderHub CRM — Packaging Stock Movement Model (PKG-2)

Immutable ledger row for every change to packaging stock. Paired with the
cached counter PackagingBox.stock_quantity (hybrid event-sourcing pattern).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, UUIDPrimaryKeyMixin


class StockMovementReason(str, enum.Enum):
    INITIAL_STOCK = "initial_stock"
    RESTOCK = "restock"
    TTN_CREATE = "ttn_create"
    TTN_DELETE = "ttn_delete"
    ADJUSTMENT = "adjustment"


class PackagingStockMovement(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "packaging_stock_movements"

    box_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("packaging_boxes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[StockMovementReason] = mapped_column(
        Enum(
            StockMovementReason,
            name="packaging_stock_movement_reason",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            create_constraint=True,
        ),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    def __repr__(self) -> str:
        return (
            f"<PackagingStockMovement box={self.box_id} delta={self.delta:+d} "
            f"reason={self.reason.value}>"
        )
