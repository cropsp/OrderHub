"""
OrderHub CRM — Delivery Tracking Schemas (WB-TRACK-1)

Wire shape for `GET /api/westernbid/tracking`. This is the ONE surface both the
MCP tool and the future `WB-TRACK-2` page read, so it deliberately carries
fields an MCP text answer does not need — recipient, city, scheduled date, order
link — rather than making the page a migration.

Status text and code are verbatim strings (task rule 3). The two `float` fields
are day counts, not money; they are classified `neutral` in
tests/test_money_field_completeness.py, which is where that decision is recorded
and enforced.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TrackedParcelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tracking_number: str | None = None
    carrier: str | None = None
    shipment_id: uuid.UUID
    order_id: uuid.UUID | None = None
    order_number: str | None = None

    # delivered | moving | problem | no_data | untracked
    state: str
    status_code: str | None = None
    status_text: str | None = None

    is_overdue: bool
    is_stalled: bool
    days_overdue: float | None = None
    days_since_movement: float | None = None

    recipient_name: str | None = None
    city_recipient: str | None = None
    recipient_country_code: str | None = None

    scheduled_delivery_at: datetime | None = None
    last_movement_at: datetime | None = None
    delivered_at: datetime | None = None
    no_data_since: datetime | None = None

    wb_status: str | None = None
    wb_created_at: datetime | None = None


class TrackingOverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    counts: dict[str, int]
    parcels: list[TrackedParcelResponse]
    # Last time the poller successfully touched any parcel. None means the daily
    # job has never run — which the caller must not mistake for "nothing moved".
    polled_at: datetime | None = None
    stalled_days: int
