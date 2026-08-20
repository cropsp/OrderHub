"""
OrderHub CRM — Parcel Alert Schemas (WB-ALERTS-1)

Wire shape for `GET /api/westernbid/alerts` and the dismiss action. The
dashboard block is the only consumer today.

Display fields (`tracking_number`, `tracking_numbers`, `recipient_name`,
`carrier`) are NOT columns on `wb_parcel_alert` — they are joined from
`wb_parcel` at read time through the same
`wb_tracking_service.extract_novapost_number` / `carrier_tracking_numbers`
the monitoring page uses. Snapshotting them onto the alert row would create a
second carrier-selection rule and let the display drift from the mirror.

`tracking_numbers` matters most on `untracked_aging`, where `tracking_number`
is NULL by definition: WB-TRACK-2 OQ1 caught exactly this trap once already —
telling an operator to "check these by hand" while showing nothing to check
with.

`age_days` is a float, and deliberately not an int: `tests/
test_money_field_completeness.py` only inspects float/Decimal fields, and
dodging that guard with an int would dodge the decision it exists to force.
It is classified `neutral` there. It is also NOT a Decimal — WB-TRACK-2's
lesson is that Decimals serialise as JSON strings, and `"10" < "5"` is how a
healthy box lit up a low-stock badge.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from schemas.wb_tracking import WbTrackingNumberRef


class ParcelAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # delivery_problem | no_data_stuck | overdue_long | untracked_aging
    kind: str
    # Short Ukrainian reason, as of the last poll that saw the condition.
    detail: str

    shipment_id: uuid.UUID
    # The Nova Poshta number. NULL on `untracked_aging` — read
    # `tracking_numbers` there.
    tracking_number: str | None = None
    tracking_numbers: list[WbTrackingNumberRef] = []
    recipient_name: str | None = None
    carrier: str | None = None

    raised_at: datetime
    # Days since the alert was raised — how long this has been waiting, which
    # is not the same number as the one inside `detail` (that one describes the
    # condition). Always live, computed on read.
    age_days: float

    # Present on the dismiss response; always NULL on the open list, which
    # excludes dismissed rows by definition.
    dismissed_at: datetime | None = None
    dismissed_by_id: uuid.UUID | None = None


class ParcelAlertListResponse(BaseModel):
    alerts: list[ParcelAlertResponse]
    # When the alert set was last reconciled. Alert sync runs inside the poll
    # pass, so the poll timestamp IS the sync timestamp — no second piece of
    # state to keep honest. NULL means the poll has never run, which the caller
    # must not read as "nothing is wrong".
    #
    # Caveat: `last_polled_at` only advances when there was something to poll,
    # so on a system with zero in-flight tracked parcels this can lag while
    # alert sync itself is running fine.
    synced_at: datetime | None = None
