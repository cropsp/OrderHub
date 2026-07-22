"""
OrderHub CRM — WesternBid Parcel Schemas (WB-1)

Read-only projection of the `wb_parcel` mirror for the admin list. Status fields
are surfaced verbatim as strings (task rule 4) — the whole point of WB-1 is to
observe WB's real value sets, so nothing is normalized or enum-mapped here.

Deliberately exposes NO numeric money field: `payment_status` is text and the
`Package` object stays opaque, so this response carries no cost/revenue value
(keeps it outside the money-visibility surface guarded by
tests/test_money_field_completeness.py).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WbParcelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shipment_id: uuid.UUID
    shipping_type: str | None = None
    carrier_type: str | None = None
    shipping_service_type: str | None = None
    # List of {"Identifier": <carrier>, "TrackingNumber": <code>} objects — NOT
    # bare strings (declaring list[str] made model_validate 500 on real data).
    tracking_numbers: list[dict] = []
    recipient_name: str | None = None
    recipient_postal_code: str | None = None
    recipient_country_code: str | None = None
    payment_status: str | None = None
    wb_status: str | None = None
    wb_created_at: datetime | None = None
    first_seen_at: datetime
    last_seen_at: datetime
