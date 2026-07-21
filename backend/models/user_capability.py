"""
OrderHub CRM — User Capability (USER-ACCESS-2)

Explicit per-user capability override. A row means "this user's `capability`
flag is fixed to `granted`, regardless of the role default". Absence of a row →
fall back to the role default (resolved in access_service.get_capabilities).

OWNER never needs a row — the resolver short-circuits to all-capabilities
(superuser, same rule as ShopScope). `capability` is stored as a plain String
validated against models.user.Capability so a future capability adds no schema
change (deliberately not a PG enum — avoids the user_role `ALTER TYPE` risk).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, UUIDPrimaryKeyMixin


class UserCapability(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "user_capability"
    __table_args__ = (
        UniqueConstraint("user_id", "capability", name="uq_user_capability_user_cap"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="capabilities")

    def __repr__(self) -> str:
        return (
            f"<UserCapability user={self.user_id} "
            f"cap={self.capability} granted={self.granted}>"
        )
