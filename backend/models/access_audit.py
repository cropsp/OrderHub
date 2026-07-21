"""
OrderHub CRM — Access Audit (USER-ACCESS-2)

Persistent record of access-control changes — both shop-access grants/revokes
(USER-ACCESS-1, previously log-only) and capability grants/revokes. One row per
change. The `access_service` docstring promised this table; it now exists.

One table for both object kinds (identical columns; "all access changes for user
X" is one query). Non-human writes (order-assignment hook, new-shop propagation)
use SYSTEM_USER_ID (constants.py) as the actor, mirroring the audit-actor
convention. Written flush-only from access_service; the router owns the commit.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, UUIDPrimaryKeyMixin


class AccessAudit(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "access_audit"

    # Who performed the change (a user id, or SYSTEM_USER_ID for automated writes).
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Whose access changed.
    target_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    # "shop_access" | "capability".
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # The shop_id (as str) for shop_access, or the capability name for capability.
    object_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # "grant" | "revoke".
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    # Provenance: manual | editor | user-create | shop-create | assignment |
    # capability-editor.
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AccessAudit actor={self.actor_id} target={self.target_user_id} "
            f"{self.action} {self.object_type}={self.object_id} src={self.source}>"
        )
