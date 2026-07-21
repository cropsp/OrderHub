"""
OrderHub CRM — Common Schemas

Shared schemas for pagination, errors, etc.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginationParams(BaseModel):
    page: int = 1
    limit: int = 50


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int
    pages: int


class ErrorResponse(BaseModel):
    detail: str


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[dict]
    products_created: int = 0
    variants_created: int = 0

    # SHOPIFY-BACKFILL extras. Default-inert so the Etsy CSV, webhook, and
    # ongoing-sync callers are unaffected; only the paginated backfill fills them.
    dry_run: bool = False
    found: int = 0          # orders seen across all pages (imported + skipped)
    would_create: int = 0   # dry-run only: orders that WOULD be created
    # month ("YYYY-MM") -> {found, already_present, created}
    by_month: dict[str, dict] = {}
    # OrderStatus value ("new", "completed", ...) -> count of orders that would
    # be / were created. Reveals how many historical orders land as NEW and hit
    # the active pipeline (Open Question 2) — invisible in the per-month counts.
    by_status: dict[str, int] = {}
    # Created/would-create line items with NO resolvable variant, i.e. no usable
    # SKU snapshot → no eventual link back to a BOM for cost recomputation.
    items_without_sku: int = 0
