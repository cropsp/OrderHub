"""
OrderHub CRM — AppSetting Model

A small key/value store for global, app-level settings that are not per-shop and
not env vars — currently just the Google Address Validation API key (ADDR-VAL-1).

Secret values are Fernet-encrypted via services/encryption_service.py before they
reach this table; `last4` holds the (non-sensitive) trailing characters so the
settings API can render a masked "••••1234" state without ever decrypting on a
read path. Contrast with the Nova Poshta keys, which are per-shop columns on the
Shop model (models/shop.py) — those are shop-scoped, this is app-scoped.
"""

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


# Setting keys. Add new global settings here rather than creating new tables.
GOOGLE_ADDRESS_VALIDATION_API_KEY = "google_address_validation_api_key"

# WesternBid credentials (WB-1). The WB account is one for all shops (unlike the
# per-shop Shopify / Nova Poshta keys), so it lives here, app-scoped. Both values
# are Fernet-encrypted: the `Login` header is equivalent to full account access,
# so it is a secret too, not just an identifier (task rule 5).
WESTERNBID_API_KEY = "westernbid_api_key"
WESTERNBID_LOGIN = "westernbid_login"


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # Trailing 4 chars of the plaintext, stored at write time so masked reads
    # never need to decrypt. Not a secret on its own.
    last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
