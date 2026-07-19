"""
OrderHub CRM — User Shop Access (USER-ACCESS-1)

Explicit per-user shop-access grant. A row means "this user may see this shop".
OWNER never needs a row (unrestricted by design — see access_service.ShopScope).
MANAGER/DESIGNER are scoped to their granted shops.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, UUIDPrimaryKeyMixin


class UserShopAccess(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "user_shop_access"
    __table_args__ = (
        UniqueConstraint("user_id", "shop_id", name="uq_user_shop_access_user_shop"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="shop_access")

    def __repr__(self) -> str:
        return f"<UserShopAccess user={self.user_id} shop={self.shop_id}>"
