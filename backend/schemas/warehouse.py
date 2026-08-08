"""WH-5 — retro-consumption backfill request + report.

The report is typed (rather than the bare dict every other backfill returns) on
purpose: it carries per-order production costs, and a `response_model` is what
puts those fields in front of tests/test_money_field_completeness.py. See that
file for the two `backfill_production_cost*` classifications and the
`view_costs-403` verdict on this route.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.order import OrderStatus
from services.finance_service import REVENUE_STATUSES


# The only statuses a retro run may touch. Imported, not re-declared: these are
# exactly the two statuses finance counts, so COGS lands where revenue already is.
# COMPLETED is reachable only from SHIPPED (models/order.py ALLOWED_TRANSITIONS),
# so a COMPLETED order necessarily shipped. CANCELLED is excluded even though a
# cancelled order can carry a TTN — it sits outside REVENUE_STATUSES, so its COGS
# would never reach the P&L.
RETRO_ELIGIBLE_STATUSES: tuple[OrderStatus, ...] = tuple(REVENUE_STATUSES)


class BoxResolution(str, Enum):
    """How the runner decided which box this order shipped in (task rule 5)."""

    ORDER_PACKAGING = "ORDER_PACKAGING"          # ① operator's own choice
    COMPUTED_BOX = "COMPUTED_BOX"                # ② the parcel calculator's suggestion
    PRODUCT_DEFAULT = "PRODUCT_DEFAULT"          # ③ one distinct product default
    PRODUCT_DEFAULT_LARGEST = "PRODUCT_DEFAULT_LARGEST"  # ④ several → largest by volume
    UNRESOLVED = "UNRESOLVED"                    # ⑤ nothing to go on


class BomCoverage(str, Enum):
    """How much of the order's line items have a recipe behind them.

    Mirrors order_consumption_service's own fold: an item counts as equipped when
    its variant's product has at least one BomItem. NONE means the WH-2 rule
    applies and the cost snapshot stays NULL even though the box is consumed.
    """

    FULL = "FULL"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


class BackfillOutcome(str, Enum):
    CONSUMED = "CONSUMED"                  # went through the consumption service
    ALREADY_CONSUMED = "ALREADY_CONSUMED"  # the service's idempotency guard said no
    FAILED = "FAILED"                      # isolated to this order, batch continued


class ConsumptionBackfillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A real write must be an explicit dry_run=false — the house rule on every
    # sibling backfill in routers/shops.py.
    dry_run: bool = True

    # Defaults to RETRO_ELIGIBLE_STATUSES. Accepts enum values ("shipped") or
    # member names ("SHIPPED"), case-insensitively, because this endpoint is
    # driven by hand from a terminal and the DB stores the NAMES.
    statuses: Optional[List[OrderStatus]] = None

    # Oldest-first tranche size. Lets a prod run be split, which both bounds the
    # transaction and makes the dev smoke possible. None = every match.
    limit: Optional[int] = Field(None, gt=0)

    # Rehearse or run one shop at a time. None = all shops (OWNER is unrestricted).
    shop_id: Optional[uuid.UUID] = None

    @field_validator("statuses", mode="before")
    @classmethod
    def _coerce_statuses(cls, value):
        if value is None or not isinstance(value, list):
            return value
        coerced = []
        for raw in value:
            if isinstance(raw, OrderStatus):
                coerced.append(raw)
                continue
            if isinstance(raw, str):
                try:
                    coerced.append(OrderStatus(raw.lower()))
                    continue
                except ValueError:
                    pass
                try:
                    coerced.append(OrderStatus[raw.upper()])
                    continue
                except KeyError:
                    pass
            coerced.append(raw)
        return coerced

    @model_validator(mode="after")
    def _statuses_are_eligible(self) -> "ConsumptionBackfillRequest":
        if self.statuses is None:
            return self
        if not self.statuses:
            raise ValueError("statuses must not be empty")
        allowed = set(RETRO_ELIGIBLE_STATUSES)
        rejected = [s.value for s in self.statuses if s not in allowed]
        if rejected:
            raise ValueError(
                "statuses may only contain "
                f"{[s.value for s in RETRO_ELIGIBLE_STATUSES]}; got {rejected}. "
                "Consuming for an order that never shipped would move stock that "
                "never left the shelf."
            )
        return self


class ConsumptionBackfillRow(BaseModel):
    """One order's line in the report. Same shape in dry-run and execute."""

    order_id: uuid.UUID
    order_number: Optional[str] = None
    external_id: str
    shop_name: str
    ordered_at: datetime
    status: OrderStatus
    currency: str

    resolution: BoxResolution
    resolved_box_id: Optional[uuid.UUID] = None
    resolved_box_name: Optional[str] = None
    # True when the runner persisted the resolved box onto order.packaging_id
    # (rules ③/④ only — ① is the operator's choice and is never overwritten).
    packaging_id_written: bool = False

    bom_coverage: BomCoverage
    outcome: BackfillOutcome
    packaging_consumed: bool = False

    # The cost the consumption service booked onto this order, in the ORDER's
    # currency. None is a real answer, not a gap: no BOM (WH-2 leaves it NULL so a
    # box-only figure cannot win the row-wise COALESCE in five aggregates), or no
    # usable FX rate (all-or-nothing).
    backfill_production_cost: Optional[Decimal] = None

    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class BoxConsumptionCount(BaseModel):
    """Units of one box consumed by this run — the input to runbook Phase 6's
    correction entry, which nets historical packaging spend against what the
    retro run booked."""

    box_id: uuid.UUID
    box_name: str
    units: int


class CurrencyCostTotal(BaseModel):
    """Costs summed PER CURRENCY. Never one cross-currency total: each order's
    snapshot is denominated in that order's own currency."""

    currency: str
    backfill_production_cost_total: Decimal
    orders: int


class ConsumptionBackfillReport(BaseModel):
    dry_run: bool
    statuses: List[OrderStatus]
    shop_id: Optional[uuid.UUID] = None
    limit: Optional[int] = None

    orders_total: int
    orders_consumed: int
    orders_already_consumed: int
    orders_failed: int

    boxes_consumed: List[BoxConsumptionCount] = Field(default_factory=list)
    cost_totals: List[CurrencyCostTotal] = Field(default_factory=list)

    # Diagnostics, restricted to orders this run actually consumed — an order the
    # idempotency guard skipped was not re-decided by this run and would be noise.
    # Identified by order_number when there is one, else external_id.
    orders_without_bom: List[str] = Field(default_factory=list)
    orders_without_box: List[str] = Field(default_factory=list)
    orders_ambiguous_default: List[str] = Field(default_factory=list)

    rows: List[ConsumptionBackfillRow] = Field(default_factory=list)
