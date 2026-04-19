"""
OrderHub CRM — Attachment Model

File attachments for orders (mockups, reference images, etc.).
Files are served via authenticated endpoint, never directly.
"""

import enum
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, UUIDPrimaryKeyMixin


class AttachmentType(str, enum.Enum):
    MOCKUP = "mockup"
    REFERENCE = "reference"
    OTHER = "other"


class Attachment(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "attachments"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"),
        nullable=False,
    )

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    attachment_type: Mapped[AttachmentType] = mapped_column(
        Enum(AttachmentType, name="attachment_type", create_constraint=True),
        default=AttachmentType.OTHER,
        nullable=False,
    )

    created_at: Mapped[None] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )

    # Relationships
    order = relationship("Order", back_populates="attachments")
    uploaded_by = relationship("User", back_populates="uploaded_attachments")

    def __repr__(self) -> str:
        return f"<Attachment {self.file_name}>"
