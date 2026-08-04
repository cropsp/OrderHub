"""
OrderHub CRM — Etsy statement import schemas (STATEMENT-IMPORT)

The import report. Every figure here is a cost or a settlement amount, so the
endpoint returning it is gated wholesale by VIEW_COSTS (`view_costs-403` in
`tests/test_money_field_completeness.py`).

Field names are chosen deliberately: `MONEY_FIELD_CLASSIFICATION` is keyed
globally by bare field name, so reusing a name like `amount` or `total_cost`
would silently inherit that name's verdict instead of forcing a decision.
"""

from decimal import Decimal

from pydantic import BaseModel, Field


class StatementUnmatchedOrder(BaseModel):
    """An order number the statement charges for, summed.

    Used for two distinct report sections:
      - `unmatched_orders` — this shop has no such order, so nothing was written
        (rule 7: never create an order, never guess a match).
      - `credit_only_orders` — the order exists and its fee came out NEGATIVE
        because Etsy refunded fees charged in a period that has not been
        imported. The value is stored as-is; this flags it for the operator.
    """

    order_external_id: str
    platform_fee_amount: Decimal


class StatementFeeOverride(BaseModel):
    """An order whose existing `platform_fee` was replaced by the statement.

    The statement is what Etsy actually charged, so it wins over a hand-entered
    or flat-rate estimate — deliberately the opposite of SHOP-FEE-1's rule, where
    a manual fee is never overwritten. Every override is reported rather than
    applied silently.
    """

    order_external_id: str
    previous_platform_fee: Decimal
    statement_platform_fee: Decimal


class StatementImportReport(BaseModel):
    dry_run: bool = Field(
        description=(
            "True: this was a rehearsal and the transaction was rolled back. "
            "Every other field is identical to what a real import would report — "
            "it is the same code path, committed or not."
        )
    )

    period: str = Field(description="Statement calendar month, 'YYYY-MM'")
    source_filename: str
    file_sha256: str
    identical_file: bool = Field(
        description="The stored period already came from a byte-identical file"
    )

    lines_imported: int
    lines_replaced: int = Field(
        description="Lines removed for this period before re-inserting"
    )

    orders_matched: int
    orders_unmatched: int
    unmatched_orders: list[StatementUnmatchedOrder] = []
    fee_overrides: list[StatementFeeOverride] = []
    credit_only_orders: list[StatementUnmatchedOrder] = []

    ads_overhead_amount: Decimal = Field(
        description="Booked to the monthly 'Etsy Ads' overhead row"
    )
    account_fee_overhead_amount: Decimal = Field(
        description="Booked to the monthly 'Etsy listing & account fees' row"
    )

    # Cross-checks, computed straight off the file — not booked anywhere.
    sales_count: int
    statement_base_amount: Decimal = Field(
        description="Sale minus buyer sales tax: what Etsy charges fees on"
    )
    refunds_count: int
    refunds_amount: Decimal = Field(
        description="Parsed and reported only; Etsy refund revenue is out of scope"
    )
    deposits_count: int
    deposits_amount: Decimal = Field(
        description="Payouts to Payoneer — independent cross-check, never a cost"
    )
