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


class WbTrackingNumberRef(BaseModel):
    """One `{Identifier, TrackingNumber}` element of `wb_parcel.tracking_numbers`.

    Both fields are optional because the source is JSONB written from WB's own
    payload; `wb_tracking_service.carrier_tracking_numbers` already drops
    non-dicts and empty numbers, and this stays permissive so a shape we have
    not seen degrades to a blank cell rather than a 500 on a monitoring page.
    """

    model_config = ConfigDict(from_attributes=True)

    Identifier: str | None = None
    TrackingNumber: str | None = None


class TrackedParcelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tracking_number: str | None = None
    carrier: str | None = None
    shipment_id: uuid.UUID
    order_id: uuid.UUID | None = None
    order_number: str | None = None

    # WB-TRACK-2: every carrier number WB reported, verbatim. `tracking_number`
    # above is the NOVA POSHTA one and is therefore NULL on all 7 untracked
    # parcels — leaving the operator told to "check these by hand" with nothing
    # to check. Carried whole rather than filtered to "the non-WesternBid one",
    # which would be a second selection rule alongside extract_novapost_number.
    tracking_numbers: list[WbTrackingNumberRef] = []

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
    # WB-TRACK-2: WB's OWN leg, demoted to secondary on the page but not
    # deleted — it is the only thing that explains the one `Parcel canceled`
    # parcel, which has no carrier number and so classifies `untracked`.
    payment_status: str | None = None
    wb_created_at: datetime | None = None


class TrackingEventResponse(BaseModel):
    """One observed transition from `wb_tracking_event` (WB-TRACK-2).

    Served lazily per parcel by `GET /tracking/{tracking_number}/events` rather
    than inlined on the list: history is only ever read for the row an operator
    opened, and shipping every parcel's log in the list payload would grow it
    without bound for a page whose job is to stay short.
    """

    model_config = ConfigDict(from_attributes=True)

    status_code: str | None = None
    status_text: str | None = None
    np_tracking_update_date: datetime | None = None
    observed_at: datetime


class TrackingRefreshResponse(BaseModel):
    """Outcome of a manual poll (WB-TRACK-2). Counts only — the caller re-reads
    `/tracking` for the new state rather than trusting a second serialisation."""

    polled: int
    created: int
    changed: int
    delivered: int
    no_data: int
    missing: int
    polled_at: datetime | None = None


class TrackingOverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    counts: dict[str, int]
    parcels: list[TrackedParcelResponse]
    # Last time the poller successfully touched any parcel. None means the daily
    # job has never run — which the caller must not mistake for "nothing moved".
    polled_at: datetime | None = None
    stalled_days: int
