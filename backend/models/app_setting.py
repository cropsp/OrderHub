"""
OrderHub CRM — AppSetting Model

A small key/value store for global, app-level settings that are not per-shop and
not env vars — the Google Address Validation API key (ADDR-VAL-1), the WesternBid
credential pair (WB-1) and the FX rate configuration (FX-CONVERSION).

Two value columns, exactly one of which is populated per row (DB CHECK
`num_nonnulls(value, value_encrypted) = 1`):

  * `value_encrypted` — SECRETS. Fernet-encrypted via services/encryption_service.py
    before they reach this table; `last4` holds the (non-sensitive) trailing
    characters so the settings API can render a masked "••••1234" state without
    ever decrypting on a read path.
  * `value` — NON-SECRET config, stored in the clear (FX-CONVERSION). Encrypting
    these would be actively harmful: decrypt_value swallows InvalidToken and
    returns None (services/address_validation.py), so an ENCRYPTION_KEY rotation
    would silently stop COGS booking with no error anywhere.

Which column a key uses is fixed per key — see SECRET_SETTING_KEYS /
PLAINTEXT_SETTING_KEYS below, enforced by tests/test_app_settings_storage.py.

Contrast with the Nova Poshta keys, which are per-shop columns on the Shop model
(models/shop.py) — those are shop-scoped, this is app-scoped.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
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

# ── FX-CONVERSION ──────────────────────────────────────────────────────────
# All non-secret, so all stored in `value` (plaintext). The key names encode the
# quote PAIR and its DIRECTION on purpose: NBU publishes UAH per 1 USD, and a
# generically-named `fx_rate` key is how a third currency — or an inverted rate —
# gets smuggled in later. See services/fx_service.py.
FX_SOURCE_URL = "fx_source_url"
FX_UAH_PER_USD_OVERRIDE = "fx_uah_per_usd_override"
FX_UAH_PER_USD_CACHED = "fx_uah_per_usd_cached"
# NBU's own `exchangedate` for the cached rate — the banking day the rate is FOR,
# which is not the day we fetched it (NBU publishes the next banking day's rate).
FX_RATE_DATE = "fx_rate_date"
# Written only on a SUCCESSFUL fetch, or staleness detection is meaningless.
FX_FETCHED_AT = "fx_fetched_at"


# Storage discipline, asserted by tests. Making `value_encrypted` nullable (to
# admit plaintext rows) removed the schema-level guarantee that secrets are
# encrypted; these sets restore it at the test level.
SECRET_SETTING_KEYS = frozenset(
    {
        GOOGLE_ADDRESS_VALIDATION_API_KEY,
        WESTERNBID_API_KEY,
        WESTERNBID_LOGIN,
    }
)

PLAINTEXT_SETTING_KEYS = frozenset(
    {
        FX_SOURCE_URL,
        FX_UAH_PER_USD_OVERRIDE,
        FX_UAH_PER_USD_CACHED,
        FX_RATE_DATE,
        FX_FETCHED_AT,
    }
)


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    # Exactly one of value_encrypted / value is set — see the module docstring.
    value_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Trailing 4 chars of the plaintext, stored at write time so masked reads
    # never need to decrypt. Not a secret on its own. Secret rows only.
    last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(value, value_encrypted) = 1",
            name="ck_app_settings_exactly_one_value",
        ),
    )
