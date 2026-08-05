"""
OrderHub CRM — Shop Schemas
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from models.shop import ShopPlatform


class ShopBackfillRequest(BaseModel):
    """SHOPIFY-BACKFILL: bounded historical Shopify import for one shop."""

    since: date
    until: date | None = None
    # dry_run defaults TRUE — the first approval gate. A real import must be an
    # explicit dry_run=false (task rule 4 + workflow's second approval gate).
    dry_run: bool = True

    @model_validator(mode="after")
    def _check_range(self) -> "ShopBackfillRequest":
        if self.until is not None and self.until < self.since:
            raise ValueError("until must be on or after since")
        return self


class ShopRefundBackfillRequest(BaseModel):
    """SHOPIFY-REFUNDS retro-fix: fetch + upsert Shopify refunds for existing orders."""

    # dry_run defaults TRUE — the second approval gate (task workflow). A real write
    # must be an explicit dry_run=false so refund rows never land on prod unreviewed.
    # No date range: the retro-fix walks every order (the ongoing poll windows by
    # `updated_at` in the scheduler instead).
    dry_run: bool = True


class ShopPlatformFeeBackfillRequest(BaseModel):
    """SHOP-FEE-1: re-price existing orders that never got a `platform_fee`.

    `since`/`until` bound the run by COALESCE(shipped_at, ordered_at) — the same
    expression finance buckets by — so an operator can leave already-settled
    partner periods alone. Both optional: unset re-prices the shop's whole
    history.
    """

    since: date | None = None
    until: date | None = None
    # dry_run defaults TRUE, like the other shop backfills. This one moves the
    # P&L and every future partner-payout base, so a real write must be an
    # explicit dry_run=false after reviewing the reported impact.
    dry_run: bool = True

    @model_validator(mode="after")
    def _check_range(self) -> "ShopPlatformFeeBackfillRequest":
        if self.since is not None and self.until is not None and self.until < self.since:
            raise ValueError("until must be on or after since")
        return self


class ShopShippingBackfillRequest(BaseModel):
    """ORDER-SHIPPING-1: capture shipping/discount/tax on orders that predate it.

    `since`/`until` bound the run by `Order.ordered_at` — NOT the
    COALESCE(shipped_at, ordered_at) the platform-fee backfill uses. This run is
    reconciled against Shopify's order feed, so it has to select the same orders
    the Shopify-side `created_at` page filter does. Both optional: unset walks the
    shop's whole history.
    """

    since: date | None = None
    until: date | None = None
    # dry_run defaults TRUE, like every other shop backfill. This one is
    # fill-only and never overwrites, but it still writes three money columns
    # across the shop's whole history — a real write must be an explicit
    # dry_run=false after reading the per-month reconciliation.
    dry_run: bool = True

    @model_validator(mode="after")
    def _check_range(self) -> "ShopShippingBackfillRequest":
        if self.since is not None and self.until is not None and self.until < self.since:
            raise ValueError("until must be on or after since")
        return self


# STATEMENT-IMPORT: Etsy orders are priced from the payment statement, which
# carries the exact per-order fee, so a flat rate must never also fire on them —
# the two paths would both write `platform_fee` and the statement's accuracy
# would be indistinguishable from an estimate. The UI happens not to render the
# input for a non-Shopify shop (FEE-UI-SHOPIFY-ONLY), but the API accepted one,
# so the rule was enforced only by omission. Enforced here on create, and in
# routers/shops.py `update_shop` on PATCH (ShopUpdate carries no platform).
ETSY_FLAT_RATE_REJECTED = (
    "Etsy shops are priced from the payment-account statement import, not a flat "
    "rate. Leave fee_percent unset and import the monthly statement instead."
)


class ShopBase(BaseModel):
    name: str = Field(..., max_length=255)
    platform: ShopPlatform
    shopify_store_url: HttpUrl | str | None = None
    np_sender_name: str | None = Field(None, max_length=255)
    np_sender_phone: str | None = Field(None, max_length=20)
    np_sender_city_ref: str | None = Field(None, max_length=36)
    np_sender_warehouse_ref: str | None = Field(None, max_length=36)
    np_sender_ref: str | None = Field(None, max_length=36)
    np_sender_contact_ref: str | None = Field(None, max_length=36)
    np_default_description: str | None = Field(None, max_length=255)
    np_default_weight_kg: float = 0.5
    np_default_volume_m3: float = 0.004
    np_default_payer_type: str = Field("Sender", max_length=20)
    np_default_payment_method: str = Field("Cash", max_length=20)
    color: str = Field("#6366F1", max_length=7)
    is_active: bool = True
    # SHOP-FEE-1: total effective per-order transaction fee, percent. None = not
    # configured (no auto fee). Nulled on read for callers without VIEW_COSTS —
    # see routers/shops.py `_visible_fee_percent`.
    fee_percent: Decimal | None = Field(None, ge=0, le=100)

    @model_validator(mode="after")
    def _no_flat_rate_on_etsy(self) -> "ShopBase":
        if self.platform == ShopPlatform.ETSY and self.fee_percent is not None:
            raise ValueError(ETSY_FLAT_RATE_REJECTED)
        return self


class ShopCreate(ShopBase):
    """Payload for creating a new shop (including raw tokens for encryption)."""
    shopify_access_token: str | None = None
    shopify_webhook_secret: str | None = None
    np_api_key: str | None = None


class ShopUpdate(BaseModel):
    """Payload for updating a shop (all fields optional)."""
    name: str | None = Field(None, max_length=255)
    shopify_store_url: HttpUrl | str | None = None
    shopify_access_token: str | None = None
    shopify_webhook_secret: str | None = None
    np_api_key: str | None = None
    np_sender_name: str | None = Field(None, max_length=255)
    np_sender_phone: str | None = Field(None, max_length=20)
    np_sender_city_ref: str | None = Field(None, max_length=36)
    np_sender_warehouse_ref: str | None = Field(None, max_length=36)
    np_sender_ref: str | None = Field(None, max_length=36)
    np_sender_contact_ref: str | None = Field(None, max_length=36)
    np_default_description: str | None = Field(None, max_length=255)
    np_default_weight_kg: float | None = None
    np_default_volume_m3: float | None = None
    np_default_payer_type: str | None = Field(None, max_length=20)
    np_default_payment_method: str | None = Field(None, max_length=20)
    color: str | None = Field(None, max_length=7)
    is_active: bool | None = None
    # SHOP-FEE-1. Must be declared here explicitly: ShopUpdate does NOT inherit
    # ShopBase, and Pydantic drops unknown keys, so an omitted field would make
    # PATCH return 200 while silently discarding the value. Sending an explicit
    # null clears the rate (exclude_unset distinguishes that from "absent").
    fee_percent: Decimal | None = Field(None, ge=0, le=100)


class ShopResponse(ShopBase):
    """Returned shop details with masked tokens."""
    id: uuid.UUID
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime
    
    # We return boolean flags instead of the tokens themselves, 
    # to let the frontend know if they are configured
    has_shopify_token: bool = False
    has_shopify_webhook_secret: bool = False
    has_np_token: bool = False
    is_np_ready: bool = False

    model_config = ConfigDict(from_attributes=True)


class ShopDetailResponse(ShopResponse):
    """Shop details including computed metrics like order count."""
    order_count: int = 0
