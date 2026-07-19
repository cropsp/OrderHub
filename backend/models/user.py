"""
OrderHub CRM — User Model

Roles: owner, manager, designer.
"""

import enum

from sqlalchemy import Boolean, Enum, String, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(str, enum.Enum):
    OWNER = "owner"
    MANAGER = "manager"
    DESIGNER = "designer"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", create_constraint=True),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict, server_default='{}', nullable=False)

    # Relationships
    assigned_orders = relationship("Order", back_populates="assigned_designer", foreign_keys="Order.assigned_designer_id")
    status_changes = relationship("OrderStatusHistory", back_populates="changed_by")
    uploaded_attachments = relationship("Attachment", back_populates="uploaded_by")
    shop_access = relationship(
        "UserShopAccess", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role.value})>"
