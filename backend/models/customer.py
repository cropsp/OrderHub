"""
OrderHub CRM — Customer Model

Customers are upserted by email. Address data lives on Order (shipping fields),
not on Customer, since one customer may use different addresses.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Customer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "customers"

    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # Relationships
    orders = relationship("Order", back_populates="customer", lazy="selectin")

    # NOTE: total_orders is NOT stored — always computed via COUNT query

    def __repr__(self) -> str:
        return f"<Customer {self.full_name} ({self.email})>"
