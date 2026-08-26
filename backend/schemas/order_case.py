"""
OrderHub CRM — Order Case Schemas (CASE-1)

Wire shape for `/api/cases`. Two consumers: the order card (cases of one order,
with their timelines) and the dashboard block (open cases across every order the
caller may see).

The Python enums live HERE rather than on the columns. `models/order_case.py`
stores plain strings — the `Capability` precedent — so this layer is the only
thing standing between the API and a bad value, which is why every write model
below types the field as an enum rather than `str`.

NO FLOAT OR DECIMAL FIELDS ANYWHERE IN THIS MODULE, deliberately.
`tests/test_money_field_completeness.py` inspects float/Decimal response fields
and forces a revenue/cost/margin/money/neutral verdict on each. A convenience
`days_overdue: float` would drag a workflow feature that handles no money into
the money-classification surface for nothing: `due_at` is on the wire, and the
countdown is a subtraction the component can do. If a numeric ever genuinely
becomes necessary here it must be a float classified `neutral` — never a
Decimal, which serialises as a JSON string and sorts as one (`schemas/
wb_alert.py:24-31`, where `"10" < "5"` lit up a low-stock badge on a full box).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.order_case import OrderCaseStatus, OrderCaseType


# ─── Notes ─────────────────────────────────────────────────

class OrderCaseNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # 'comment' (a human wrote it) | 'system' (a status transition).
    kind: str
    text: str
    created_at: datetime
    # Resolved in the router for display; the column is author_id. Present on
    # system rows too — task rule 3 wants transitions attributed.
    author_id: uuid.UUID
    author_name: str | None = None


class OrderCaseNoteCreate(BaseModel):
    """Only `text`. `kind` is NOT accepted from the wire: a client must not be
    able to forge a status-transition record, which is the one row type the
    timeline is expected to trust."""

    text: str = Field(min_length=1, max_length=5000)


# ─── Cases ─────────────────────────────────────────────────

class OrderCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    case_type: str
    title: str
    status: str
    next_action: str | None = None
    due_at: datetime | None = None

    owner_id: uuid.UUID | None = None
    owner_name: str | None = None
    created_by_id: uuid.UUID
    created_by_name: str | None = None

    resolved_at: datetime | None = None
    resolution_note: str | None = None

    created_at: datetime
    updated_at: datetime

    notes: list[OrderCaseNoteResponse] = []


class OrderCaseCreate(BaseModel):
    case_type: OrderCaseType
    title: str = Field(min_length=1, max_length=500)
    next_action: str | None = Field(default=None, max_length=2000)
    due_at: datetime | None = None
    owner_id: uuid.UUID | None = None


class OrderCaseUpdate(BaseModel):
    """Every field optional — this is a PATCH.

    `status` moving to `resolved` is what stamps `resolved_at`; the service owns
    that, not the client, so there is no `resolved_at` field here. Same reason
    `notes` is absent: notes are append-only through their own endpoint.
    """

    case_type: OrderCaseType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    status: OrderCaseStatus | None = None
    next_action: str | None = Field(default=None, max_length=2000)
    due_at: datetime | None = None
    owner_id: uuid.UUID | None = None
    # Only meaningful alongside `status=resolved`; ignored otherwise.
    resolution_note: str | None = Field(default=None, max_length=2000)


# ─── Dashboard ─────────────────────────────────────────────

class OpenCaseRow(BaseModel):
    """A dashboard row: the case plus just enough of its order to be clickable
    and recognisable without a second request.

    Deliberately NOT a subclass of `OrderCaseResponse`: that would carry the
    whole note timeline of every open case into the dashboard payload, and the
    block renders none of it. The row shows what a manager scans — who, what,
    what next, by when.

    No money fields — `total_price` would be `revenue`-classified and would drag
    this route onto the money surface (see the module docstring).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    case_type: str
    title: str
    status: str
    next_action: str | None = None
    due_at: datetime | None = None

    owner_id: uuid.UUID | None = None
    owner_name: str | None = None

    created_at: datetime

    order_number: str | None = None
    order_external_id: str | None = None
    customer_name: str | None = None
    shop_id: uuid.UUID
    shop_name: str | None = None


class OpenCasesResponse(BaseModel):
    """Two groups, matching the dashboard's two headings.

    Split server-side rather than in the component because the ordering rule
    differs per group: `in_progress` is overdue-first, `waiting` is
    due-date-first. Keeping that beside the query is what stops a second,
    drifting definition of "overdue" appearing in the frontend — the mistake
    `ParcelAlertsCard`'s docblock calls out for alerts.
    """

    # "В роботі" — overdue first, then by due date, then newest.
    in_progress: list[OpenCaseRow] = []
    # "Чекаємо" — same ordering; the ball is not in our court.
    waiting: list[OpenCaseRow] = []
