"""
OrderHub CRM — Shopify Synchronization Service (GraphQL Edition)
Pulls orders from Shopify using GraphQL Admin API and upserts them into OrderHub.
"""

import asyncio
import httpx
import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import logging
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Date, cast, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models.shop import Shop, ShopPlatform
from models.order import Order, OrderRefund, OrderStatus
from models.product import ProductVariant
from schemas.common import ImportResult
from schemas.order import OrderCreate, OrderItemCreate
from services.catalog_import import ensure_catalog_row, _weight_to_grams
from services.catalog_service import CatalogService
from services.encryption_service import decrypt_value
from services.order_service import compute_platform_fee, create_order

SHOPIFY_API_VERSION = "2024-04"

# Orders per page. Shopify caps `first` at 250; 50 keeps per-page query cost well
# under the default 1000-point bucket, leaving headroom for the nested lineItems.
ORDERS_PAGE_SIZE = 50

# Throttle handling (task rule 5). The GraphQL Admin API is cost-based: each
# response carries extensions.cost.throttleStatus. We retry a THROTTLED page a
# bounded number of times, sleeping by the reported deficit / restoreRate.
MAX_THROTTLE_RETRIES = 6
DEFAULT_RESTORE_RATE = 50.0

ORDERS_QUERY = """
query GetOrders($first: Int!, $after: String, $query: String) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT, reverse: true) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        name
        createdAt
        closedAt
        cancelledAt
        displayFinancialStatus
        displayFulfillmentStatus
        totalPriceSet {
          shopMoney {
            amount
            currencyCode
          }
        }
        # ORDER-SHIPPING-1 — what the customer paid, decomposed. shopMoney only,
        # matching the convention of every other money field in this file.
        #
        # `subtotalPriceSet` is fetched but NOT stored: it is already NET of
        # discounts, so it exists here purely to check Shopify's own invariant
        # (subtotal + shipping + tax == total). The stored decomposition is
        # against the PRE-discount line-item prices below, which is what the
        # order card sums.
        subtotalPriceSet {
          shopMoney {
            amount
          }
        }
        totalShippingPriceSet {
          shopMoney {
            amount
          }
        }
        totalDiscountsSet {
          shopMoney {
            amount
          }
        }
        totalTaxSet {
          shopMoney {
            amount
          }
        }
        note
        customer {
          firstName
          lastName
          email
        }
        shippingAddress {
          name
          phone
          address1
          address2
          city
          provinceCode
          zip
          countryCodeV2
        }
        lineItems(first: 50) {
          edges {
            node {
              title
              quantity
              originalUnitPriceSet {
                shopMoney {
                  amount
                  currencyCode
                }
              }
              variant {
                id
                sku
                title
                product {
                  id
                  title
                }
                inventoryItem {
                  measurement {
                    weight {
                      value
                      unit
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

# PC-F-1 — on-demand featured-image lookup for a single product. Deliberately
# separate from ORDERS_QUERY: order sync must never pull images.
PRODUCT_IMAGE_QUERY = """
query GetProductFeaturedImage($id: ID!) {
  product(id: $id) {
    id
    featuredImage {
      url
    }
  }
}
"""

# SHOPIFY-REFUNDS — refund capture (Model 2). Deliberately separate from ORDERS_QUERY:
# refunds post long after the order, so this path windows by `updated_at` (a refund
# bumps the order's updatedAt) rather than `created_at`, and asks only for what a refund
# row needs. `Order.refunds` is a plain list (per-order refund counts are tiny), and each
# refund carries its own `createdAt` (the Model-2 date anchor) + `totalRefundedSet`.
REFUNDS_QUERY = """
query GetOrderRefunds($first: Int!, $after: String, $query: String) {
  orders(first: $first, after: $after, query: $query, sortKey: UPDATED_AT, reverse: true) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        refunds {
          id
          createdAt
          totalRefundedSet {
            shopMoney {
              amount
              currencyCode
            }
          }
        }
      }
    }
  }
}
"""


def _parse_shopify_gid(gid: Optional[str]) -> str:
    """Extract numeric tail from a Shopify GID like 'gid://shopify/Product/12345'."""
    if not gid:
        return ""
    return gid.rsplit("/", 1)[-1]


def _to_decimal(raw: Any) -> Decimal:
    if raw in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _to_decimal_or_none(raw: Any) -> Optional[Decimal]:
    """Like `_to_decimal`, but absence stays absent (ORDER-SHIPPING-1).

    `_to_decimal` maps a missing value to `Decimal("0")`, which is correct for a
    total that must exist but catastrophic for the nullable money columns: it
    would write 0.00 — "this order shipped free" — where the truth is "the
    payload never told us". NULL is the only honest answer there, so this variant
    is what the shipping/discount/tax mappers use.

    Shopify's MoneyBag fields are non-null, so a real order node always yields a
    real figure (0.00 included, which IS a fact). None here means the key was
    absent: an older API version, a REST payload that omits it, or a partial
    fixture.
    """
    if raw in (None, ""):
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


# ORDER-SHIPPING-1 — money is stored at 2dp, so anything under a cent is
# rounding, not an imbalance.
BALANCE_TOLERANCE = Decimal("0.01")


def check_order_balance(
    *,
    total: Optional[Decimal],
    shipping: Optional[Decimal],
    discount: Optional[Decimal],
    tax: Optional[Decimal],
    subtotal: Optional[Decimal] = None,
    items_gross: Optional[Decimal] = None,
) -> Optional[str]:
    """Does the captured decomposition add up? Returns a reason, or None if it does.

    Two independent checks, because they fail for different reasons and only one
    of them means the captured figures are suspect:

      "shopify" — subtotal + shipping + tax != total. This is Shopify's OWN
                  invariant (`subtotalPriceSet` is already net of discounts), so
                  a failure means the three figures we are about to store are
                  internally inconsistent. Verified to hold on 28/28 live
                  Lamamarka orders, including every one of the top-25 by discount
                  value.

      "items"   — items_gross - discount + shipping + tax != total, where
                  items_gross is SUM(qty * PRE-discount unit price). This is the
                  identity the order card renders. It can fail while "shopify"
                  passes, and then the problem is our line-item snapshot rather
                  than the money: `lineItems(first: 50)` truncates a >50-line
                  order, and post-hoc order edits move lines without moving the
                  order totals.

    The known future breaker of "items" is a cart-level FREE SHIPPING discount:
    `ShippingLine.discountedPriceSet` only folds those in from API version
    2024-07, and this client pins 2024-04 (SHOPIFY_API_VERSION above). No such
    discount exists in the data today — every discountApplication on record
    targets LINE_ITEM, never SHIPPING_LINE — but a future promo would land here.

    Callers store the figures regardless and report the reason: the imbalance is
    information about an order, not grounds for refusing to import it.
    """
    if total is None:
        return None
    # Nothing was captured, so there is no decomposition to disagree with the
    # total. Absence is already reported by the columns staying NULL; flagging it
    # here as well would turn every payload that predates these fields into a
    # false positive.
    if shipping is None and discount is None and tax is None:
        return None
    ship = shipping or Decimal("0")
    disc = discount or Decimal("0")
    vat = tax or Decimal("0")

    if subtotal is not None:
        if abs(subtotal + ship + vat - total) > BALANCE_TOLERANCE:
            return "shopify"
    # No items means nothing to reconcile against — the webhook path creates no
    # OrderItem rows at all, and a 0 subtotal there would be a false positive.
    if items_gross is not None and items_gross > 0:
        if abs(items_gross - disc + ship + vat - total) > BALANCE_TOLERANCE:
            return "items"
    return None


def extract_money_breakdown(node: dict) -> Dict[str, Optional[Decimal]]:
    """Pull the ORDER-SHIPPING-1 figures out of a GraphQL order node.

    Shared by the sync mapper and the backfill so the two can never map the same
    payload differently. `subtotal` is returned for the balance check only and is
    never stored.
    """
    def _amount(field: str) -> Optional[Decimal]:
        return _to_decimal_or_none(
            ((node.get(field) or {}).get("shopMoney") or {}).get("amount")
        )

    return {
        "shipping_revenue": _amount("totalShippingPriceSet"),
        # Shopify reports discounts POSITIVE; keep that sign, subtract at render.
        "discount_total": _amount("totalDiscountsSet"),
        "tax_total": _amount("totalTaxSet"),
        "subtotal": _amount("subtotalPriceSet"),
    }


def extract_money_breakdown_rest(data: dict) -> Dict[str, Optional[Decimal]]:
    """The same figures out of a REST webhook payload (ORDER-SHIPPING-1).

    Deliberately parked next to `extract_money_breakdown` rather than inside the
    webhook router: the two Shopify ingest paths read structurally different JSON
    for the same three values, and keeping the mappings adjacent is what stops
    one being updated without the other.

      GraphQL                          REST / webhook
      -----------------------------    ------------------------------------
      totalShippingPriceSet.shopMoney  total_shipping_price_set.shop_money
      totalDiscountsSet.shopMoney      total_discounts        (a bare string)
      totalTaxSet.shopMoney            total_tax              (a bare string)
      subtotalPriceSet.shopMoney       subtotal_price         (a bare string)

    Note the asymmetry: only shipping arrives as a money-set in REST. If that key
    is absent we fall back to summing `shipping_lines[].discounted_price`, which
    is the same number Shopify totals into it.
    """
    shipping = _to_decimal_or_none(
        ((data.get("total_shipping_price_set") or {}).get("shop_money") or {}).get("amount")
    )
    if shipping is None:
        lines = data.get("shipping_lines") or []
        parts = [_to_decimal_or_none(ln.get("discounted_price")) for ln in lines if ln]
        present = [p for p in parts if p is not None]
        shipping = sum(present, Decimal("0")) if present else None

    return {
        "shipping_revenue": shipping,
        # REST reports discounts POSITIVE too; same convention as GraphQL.
        "discount_total": _to_decimal_or_none(data.get("total_discounts")),
        "tax_total": _to_decimal_or_none(data.get("total_tax")),
        "subtotal": _to_decimal_or_none(data.get("subtotal_price")),
    }


def items_gross_from_node(node: dict) -> Decimal:
    """SUM(quantity * PRE-discount unit price) over a GraphQL order node.

    Mirrors what `OrderItem.unit_price` will hold (the mapper stores
    `originalUnitPriceSet`), which is what the order card sums for its "Items
    subtotal" row — so this is the left-hand side of the "items" balance check.
    """
    total = Decimal("0")
    for li_edge in ((node.get("lineItems") or {}).get("edges")) or []:
        li = (li_edge.get("node") if li_edge else None) or {}
        unit = _to_decimal(
            ((li.get("originalUnitPriceSet") or {}).get("shopMoney") or {}).get("amount")
        )
        total += unit * Decimal(str(int(li.get("quantity") or 1)))
    return total


def map_shopify_status(
    fulfillment_status: Optional[str], cancelled_at: Optional[str]
) -> OrderStatus:
    """Map a Shopify order's fulfilment state onto an OrderHub status.

    Settled decision (SHOPIFY-BACKFILL):
      - cancelled                → CANCELLED
      - FULFILLED                → COMPLETED  (terminal; feeds YTD finance)
      - PARTIALLY_FULFILLED      → IN_PRODUCTION
      - UNFULFILLED / anything else → NEW  (genuinely still open)

    Only SHIPPED/COMPLETED count in finance (finance_service.REVENUE_STATUSES),
    so mapping FULFILLED → COMPLETED is what makes the backfill fix the P&L. A
    fresh live order is UNFULFILLED → NEW, matching the pre-backfill behaviour.
    """
    if cancelled_at:
        return OrderStatus.CANCELLED
    if fulfillment_status == "FULFILLED":
        return OrderStatus.COMPLETED
    if fulfillment_status == "PARTIALLY_FULFILLED":
        return OrderStatus.IN_PRODUCTION
    return OrderStatus.NEW


def _build_orders_query_filter(
    since: Optional[date], until: Optional[date]
) -> Optional[str]:
    """Build the Shopify `query:` search string for a created_at date range.

    Shopify search syntax: `created_at:>=2026-01-01 created_at:<=2026-07-21`.
    Returns None when no bounds are given (ongoing sync = unfiltered).
    """
    parts: list[str] = []
    if since:
        parts.append(f"created_at:>={since.isoformat()}")
    if until:
        parts.append(f"created_at:<={until.isoformat()}")
    return " ".join(parts) or None


def _build_refund_query_filter(updated_since: Optional[datetime]) -> Optional[str]:
    """Build the Shopify `query:` search string for the refund sync.

    Filters by `updated_at` (not `created_at`): a refund bumps its order's `updatedAt`,
    so a rolling `updated_at:>=…` window catches refunds posted long after the order —
    the case the order sync (windowed by `created_at`, skip-on-existing) never revisits.
    Returns None for the full retro-fix (walk every order).
    """
    if updated_since is None:
        return None
    return f"updated_at:>={updated_since.isoformat()}"


def _parse_shopify_dt(raw: Optional[str]) -> Optional[datetime]:
    """Parse a Shopify ISO-8601 timestamp (…Z) into an aware datetime."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class ShopifyThrottledError(Exception):
    """Raised when a GraphQL response reports a THROTTLED error. Carries the
    computed seconds to wait before retrying the same page."""

    def __init__(self, retry_after: float):
        super().__init__(f"Shopify throttled; retry after {retry_after:.2f}s")
        self.retry_after = retry_after


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(httpx.HTTPError),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _post_orders_page(
    shop_url: str, access_token: str, variables: dict, query: str = ORDERS_QUERY
) -> dict:
    """POST one page of an orders-shaped query and return the FULL JSON body (data +
    extensions). Retries transient HTTP errors (tenacity); raises
    ShopifyThrottledError on a THROTTLED GraphQL error so the caller can back off.

    `query` defaults to ORDERS_QUERY (order sync); the refund sync passes REFUNDS_QUERY.
    Both are `orders(...)` connection queries, so the same page/throttle plumbing serves.
    """
    if not shop_url.startswith("http"):
        shop_url = f"https://{shop_url}"
    url = f"{shop_url.rstrip('/')}/admin/api/{SHOPIFY_API_VERSION}/graphql.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    payload = {"query": query, "variables": variables}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()

    errors = body.get("errors") or []
    if any((e.get("extensions") or {}).get("code") == "THROTTLED" for e in errors):
        cost = (body.get("extensions") or {}).get("cost") or {}
        throttle = cost.get("throttleStatus") or {}
        requested = float(cost.get("requestedQueryCost") or 0)
        available = float(throttle.get("currentlyAvailable") or 0)
        restore = float(throttle.get("restoreRate") or DEFAULT_RESTORE_RATE) or DEFAULT_RESTORE_RATE
        deficit = max(requested - available, 0.0)
        raise ShopifyThrottledError(deficit / restore if deficit else 1.0)

    if errors and not body.get("data"):
        logger.error("Shopify GraphQL Fatal Errors: %s", json.dumps(errors, indent=2))
        raise Exception(f"Shopify API Error: {errors[0].get('message')}")

    return body


async def _fetch_orders_page(
    shop_url: str, access_token: str, variables: dict, query: str = ORDERS_QUERY
) -> dict:
    """Fetch one page, transparently backing off on THROTTLED up to
    MAX_THROTTLE_RETRIES times (task rule 5 — do not retry blindly)."""
    for attempt in range(1, MAX_THROTTLE_RETRIES + 1):
        try:
            return await _post_orders_page(shop_url, access_token, variables, query)
        except ShopifyThrottledError as exc:
            if attempt == MAX_THROTTLE_RETRIES:
                raise
            wait = max(exc.retry_after, 1.0)
            logger.warning(
                "Shopify THROTTLED (attempt %d/%d) — sleeping %.2fs",
                attempt, MAX_THROTTLE_RETRIES, wait,
            )
            await asyncio.sleep(wait)
    raise RuntimeError("unreachable")  # pragma: no cover


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, Exception)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True
)
async def call_shopify_graphql(shop_url: str, access_token: str, query: str, variables: dict = None) -> dict:
    """Make an authenticated call to Shopify GraphQL Admin API."""
    # Ensure shop_url has a scheme
    if not shop_url.startswith("http"):
        shop_url = f"https://{shop_url}"

    url = f"{shop_url.rstrip('/')}/admin/api/{SHOPIFY_API_VERSION}/graphql.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }
    payload = {"query": query, "variables": variables or {}}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            logger.info(f"Calling Shopify GraphQL at {url}")
            response = await client.post(url, headers=headers, json=payload)
            logger.info(f"Shopify Response Status: {response.status_code}")

            response.raise_for_status()
            data = response.json()

            if "errors" in data and not data.get("data"):
                logger.error(f"Shopify GraphQL Fatal Errors: {json.dumps(data['errors'], indent=2)}")
                raise Exception(f"Shopify API Error: {data['errors'][0].get('message')}")

            if "errors" in data:
                logger.warning(f"Shopify GraphQL Partial Errors: {len(data['errors'])} errors found, but data was returned.")

            return data.get("data", {})
        except httpx.HTTPStatusError as e:
            logger.error(f"Shopify Sync HTTP Error: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Shopify Connection Error: {e.response.status_code}")
        except Exception as e:
            logger.exception("Shopify GraphQL call failed")
            raise Exception(f"Shopify Sync failed: {str(e)}")

def _bump_month(by_month: Dict[str, Dict[str, int]], month: str, key: str) -> None:
    bucket = by_month.setdefault(
        month, {"found": 0, "already_present": 0, "created": 0}
    )
    bucket[key] += 1


def _line_item_sku(li_node: dict) -> Optional[str]:
    """The SKU that will snapshot onto the OrderItem, or None when the line item
    has no resolvable variant (custom line item / deleted product) — such an item
    can never link back to a catalog Product, hence never to a BOM for cost.

    Pure (no DB, no API): the real write path (_write_order_node) and the dry-run
    counter share this single definition so the two can never drift. Mirrors the
    catalog SKU: the Shopify SKU when present, else a synthetic product/variant id.
    """
    variant_node = li_node.get("variant")
    if not (variant_node and variant_node.get("product")):
        return None
    raw_sku = (variant_node.get("sku") or "").strip()
    if raw_sku:
        return raw_sku
    ext_p = _parse_shopify_gid((variant_node.get("product") or {}).get("id"))
    ext_v = _parse_shopify_gid(variant_node.get("id"))
    return f"shopify-{ext_p}-{ext_v}"


def _count_items_without_sku(node: dict) -> int:
    """Count line items on an order node that will NOT get a usable SKU snapshot.
    Pure — safe to call in dry-run mode where no catalog rows are written."""
    edges = ((node.get("lineItems") or {}).get("edges")) or []
    return sum(
        1 for e in edges if _line_item_sku((e.get("node") if e else None) or {}) is None
    )


async def _write_order_node(
    db: AsyncSession,
    shop: Shop,
    system_user,
    node: dict,
    external_id: str,
    catalog_service: CatalogService,
    catalog_cache: Dict[str, Dict[str, Any]],
    counters: Dict[str, int],
) -> None:
    """Materialise one Shopify order node: auto-create catalog rows, then create
    the Order with the mapped status + a single opening audit row. Never routes
    through change_order_status (see create_order docstring — avoids MAT-4
    consumption / designer auto-assign side-effects on historical imports)."""
    items_payload: list[OrderItemCreate] = []
    line_items_edges = ((node.get("lineItems") or {}).get("edges")) or []

    for li_edge in line_items_edges:
        li = (li_edge.get("node") if li_edge else None) or {}
        variant_node = li.get("variant")

        price_money = ((li.get("originalUnitPriceSet") or {}).get("shopMoney")) or {}
        price_amount = _to_decimal(price_money.get("amount"))
        line_currency = price_money.get("currencyCode") or "USD"

        # Same resolution the dry-run counter uses; None when unlinkable.
        item_sku = _line_item_sku(li)

        variant_obj: Optional[ProductVariant] = None
        if variant_node and variant_node.get("product"):
            ext_p = _parse_shopify_gid((variant_node.get("product") or {}).get("id"))
            ext_v = _parse_shopify_gid(variant_node.get("id"))
            sku = item_sku  # non-None in this branch (variant + product present)

            weight_subtree = (
                ((variant_node.get("inventoryItem") or {}).get("measurement") or {}).get("weight")
            )
            weight_g = _weight_to_grams(weight_subtree)

            raw_title = variant_node.get("title")
            variant_name = raw_title if raw_title and raw_title != "Default Title" else None

            try:
                variant_obj = await ensure_catalog_row(
                    db,
                    shop,
                    catalog_service,
                    external_product_id=ext_p,
                    product_title=(variant_node.get("product") or {}).get("title") or "Unknown Item",
                    sku=sku,
                    variant_name=variant_name,
                    external_variant_ref=ext_v,
                    weight_g=weight_g,
                    price=price_amount,
                    catalog_cache=catalog_cache,
                    counters=counters,
                )
            except Exception:
                logger.exception(
                    "Catalog auto-create failed for order=%s line_item_title=%s; continuing",
                    external_id, li.get("title"),
                )

        items_payload.append(OrderItemCreate(
            title=li.get("title") or "Unknown Item",
            quantity=int(li.get("quantity") or 1),
            unit_price=float(price_amount),
            currency=line_currency,
            sku=item_sku,  # durable snapshot: survives variant deletion (SET NULL)
            product_variant_id=variant_obj.id if variant_obj else None,
        ))

    # Flush newly-added Product/Variant rows so _apply_variant_snapshot's
    # SELECT inside create_order finds them in this transaction.
    await db.flush()

    customer = node.get("customer") or {}
    email = customer.get("email") or f"unknown_{external_id}@example.com"
    first_name = customer.get('firstName', '') or ''
    last_name = customer.get('lastName', '') or ''
    full_name = f"{first_name} {last_name}".strip() or "Unknown Shopify Customer"

    shipping = node.get("shippingAddress") or {}
    money = node.get("totalPriceSet", {}).get("shopMoney", {}) or {}

    # Status mapping (SHOPIFY-BACKFILL). Fresh live orders are UNFULFILLED → NEW,
    # so the ongoing sync is unchanged; historical fulfilled orders → COMPLETED.
    fulfillment = node.get("displayFulfillmentStatus")
    financial = node.get("displayFinancialStatus")
    mapped_status = map_shopify_status(fulfillment, node.get("cancelledAt"))
    completed_at = None
    if mapped_status == OrderStatus.COMPLETED:
        completed_at = _parse_shopify_dt(node.get("closedAt")) or _parse_shopify_dt(
            node.get("createdAt")
        )
    history_comment = (
        f"Imported from Shopify (fulfillment={fulfillment}, financial={financial})"
    )

    # SHOP-FEE-1: the shop's effective transaction rate applied to the order
    # total, frozen here. Computed from the Decimal amount rather than the float
    # at total_price= below, so no binary-float error reaches the money column.
    # A CANCELLED order never enters REVENUE_STATUSES, so a fee on it is inert in
    # the P&L but wrong on the order card — skip it, using the SAME predicate the
    # backfill uses so the two paths cannot drift.
    platform_fee = None
    if mapped_status is not OrderStatus.CANCELLED:
        platform_fee = compute_platform_fee(
            _to_decimal(money.get("amount")), shop.fee_percent
        )
    if platform_fee is not None:
        # Provenance without a schema change. The literal "platform_fee: <amt>"
        # token is REQUIRED, not cosmetic: _FINANCIAL_COMMENT_RE in order_service
        # matches exactly that shape, so this addendum inherits VIEW_COSTS
        # redaction in the order timeline. Any other wording leaks the fee to
        # designers, who see import comments verbatim.
        history_comment += f", platform_fee: {platform_fee} @ {shop.fee_percent}%"

    # ORDER-SHIPPING-1: capture what the customer paid, decomposed, instead of
    # leaving the card to reconstruct shipping as total - items (which silently
    # absorbs the discount and the tax). Stored as reported; never derived here.
    breakdown = extract_money_breakdown(node)
    imbalance = check_order_balance(
        total=_to_decimal_or_none(money.get("amount")),
        shipping=breakdown["shipping_revenue"],
        discount=breakdown["discount_total"],
        tax=breakdown["tax_total"],
        subtotal=breakdown["subtotal"],
        items_gross=items_gross_from_node(node),
    )
    if imbalance:
        # Store anyway and flag: an imbalance is information about the order, not
        # grounds for refusing it. "items" almost always means our line-item
        # snapshot is short (>50 lines, or a post-hoc order edit), which leaves
        # the three captured figures perfectly good.
        counters["unbalanced"] = counters.get("unbalanced", 0) + 1
        logger.warning(
            "ORDER-SHIPPING-1 balance check failed (%s) for order %s (%s): "
            "total=%s shipping=%s discount=%s tax=%s subtotal=%s",
            imbalance, node.get("name"), external_id,
            money.get("amount"), breakdown["shipping_revenue"],
            breakdown["discount_total"], breakdown["tax_total"], breakdown["subtotal"],
        )

    order_create_payload = OrderCreate(
        external_id=external_id,
        shop_id=shop.id,
        # Human order name (e.g. "91890_1816"); stored dedicated now, not just a
        # title fallback, so the card can cross-reference against Shopify (ORDER-CARD-1).
        order_number=node.get("name"),
        title=(items_payload[0].title if items_payload
               else node.get("name") or f"Order #{external_id}"),
        total_price=float(money.get("amount", 0) or 0),
        currency=money.get("currencyCode", "USD"),
        ordered_at=datetime.fromisoformat(node["createdAt"].replace("Z", "+00:00")),
        items=items_payload,

        shipping_name=shipping.get("name") or full_name,
        shipping_phone=shipping.get("phone") or None,
        shipping_street_1=shipping.get("address1") or None,
        shipping_street_2=shipping.get("address2") or None,
        shipping_city=shipping.get("city") or None,
        shipping_state=shipping.get("provinceCode") or None,
        shipping_zip=shipping.get("zip") or None,
        shipping_country=shipping.get("countryCodeV2") or None,

        customer_note=node.get("note"),
        email=email,
        full_name=full_name,
    )

    await create_order(
        db,
        order_create_payload,
        system_user,
        status=mapped_status,
        completed_at=completed_at,
        history_comment=history_comment,
        platform_fee=platform_fee,
        shipping_revenue=breakdown["shipping_revenue"],
        discount_total=breakdown["discount_total"],
        tax_total=breakdown["tax_total"],
    )
    logger.info(
        "Synced order %s → %s: %s",
        external_id, mapped_status.value, order_create_payload.title,
    )


async def sync_shop_orders(
    db: AsyncSession,
    shop: Shop,
    system_user,
    *,
    since: Optional[date] = None,
    until: Optional[date] = None,
    dry_run: bool = False,
    stop_on_existing: bool = True,
) -> ImportResult:
    """Sync orders for a Shopify shop into the database, auto-creating Product/Variant catalog rows.

    Paginated across ALL matching orders (task rule 1 — the 50-order ceiling is
    the root defect). Skip-on-existing semantics: orders dedup on
    `(external_id, shop_id)`; products dedup on `(shop_id, external_ref)`;
    variants dedup on shop-wide SKU. Re-runs produce zero new rows (idempotent).

    Parameters:
      - since / until: created_at date range → Shopify `query:` filter. Both None
        = unbounded (ongoing sync).
      - dry_run: walk pages + dedup checks and count, but write NOTHING
        (task rule 4 — the first approval gate).
      - stop_on_existing: ONGOING mode (default). Orders come newest-first, so once
        a page contains an already-imported order everything below it is known —
        stop paging. This bounds the 15-min job to ~1 page in steady state while
        still catching up across pages when a burst of >50 arrives. The BACKFILL
        passes stop_on_existing=False to walk the entire date range regardless.
    """
    logger.info(
        "Starting sync for shop: %s (%s) since=%s until=%s dry_run=%s",
        shop.name, shop.id, since, until, dry_run,
    )

    if shop.platform != ShopPlatform.SHOPIFY:
        logger.warning(f"Shop {shop.name} is not a Shopify shop, skipping.")
        return ImportResult(imported=0, skipped=0, errors=[], dry_run=dry_run)

    if not shop.shopify_store_url or not shop.shopify_access_token_encrypted:
        logger.warning(f"Shop {shop.name} is missing Shopify credentials.")
        return ImportResult(imported=0, skipped=0, errors=[], dry_run=dry_run)

    token = decrypt_value(shop.shopify_access_token_encrypted)
    shop_url = str(shop.shopify_store_url)
    query_filter = _build_orders_query_filter(since, until)

    catalog_service = CatalogService(db)
    catalog_cache: Dict[str, Dict[str, Any]] = {}
    counters: Dict[str, int] = {
        "products_created": 0,
        "variants_created": 0,
        # ORDER-SHIPPING-1: orders whose captured shipping/discount/tax did not
        # reconcile to the total. Written anyway; counted so a mapping drift
        # surfaces in the import report rather than only in the log.
        "unbalanced": 0,
    }
    errors: list[dict] = []
    by_month: Dict[str, Dict[str, int]] = {}
    by_status: Dict[str, int] = {}
    imported = 0
    skipped = 0
    found = 0
    would_create = 0
    items_without_sku = 0

    after: Optional[str] = None
    while True:
        try:
            body = await _fetch_orders_page(
                shop_url,
                token,
                {"first": ORDERS_PAGE_SIZE, "after": after, "query": query_filter},
            )
        except Exception as e:
            logger.error(f"Failed to fetch orders from Shopify: {str(e)}")
            raise

        conn = (body.get("data") or {}).get("orders") or {}
        orders_edges = conn.get("edges") or []
        page_info = conn.get("pageInfo") or {}
        logger.info(f"Fetched {len(orders_edges)} orders in this page.")

        page_had_existing = False

        for edge in orders_edges:
            node = edge.get("node", {}) or {}
            external_id = _parse_shopify_gid(node.get("id"))
            created_raw = node.get("createdAt") or ""
            month = created_raw[:7] if len(created_raw) >= 7 else "unknown"

            try:
                found += 1
                _bump_month(by_month, month, "found")

                existing = await db.execute(
                    select(Order).where(
                        Order.external_id == external_id, Order.shop_id == shop.id
                    )
                )
                if existing.scalar_one_or_none():
                    skipped += 1
                    page_had_existing = True
                    _bump_month(by_month, month, "already_present")
                    continue

                # This order WILL be created (dry-run or real). Classify it the
                # same way in both paths so the dry-run preview matches the import:
                # the landing OrderHub status (does it flood the pipeline as NEW?)
                # and any line items that would arrive without a usable SKU.
                mapped_status = map_shopify_status(
                    node.get("displayFulfillmentStatus"), node.get("cancelledAt")
                )
                by_status[mapped_status.value] = by_status.get(mapped_status.value, 0) + 1
                items_without_sku += _count_items_without_sku(node)

                if dry_run:
                    would_create += 1
                    _bump_month(by_month, month, "created")
                    continue

                await _write_order_node(
                    db, shop, system_user, node, external_id,
                    catalog_service, catalog_cache, counters,
                )
                imported += 1
                _bump_month(by_month, month, "created")

            except Exception as e:
                logger.exception(f"Shopify sync failed for order {external_id}")
                errors.append({"external_id": external_id, "error": str(e)})

        # Ongoing mode: newest-first ordering means an already-imported order on
        # this page marks the catch-up boundary — stop paging.
        if stop_on_existing and page_had_existing:
            break
        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")

        # Proactive throttle backoff (task rule 5): if the next page's cost would
        # exceed the currently-available budget, sleep by the deficit / restoreRate.
        cost = (body.get("extensions") or {}).get("cost") or {}
        throttle = cost.get("throttleStatus") or {}
        available = throttle.get("currentlyAvailable")
        requested = float(cost.get("requestedQueryCost") or 0)
        restore = float(throttle.get("restoreRate") or DEFAULT_RESTORE_RATE) or DEFAULT_RESTORE_RATE
        if available is not None and float(available) < requested:
            await asyncio.sleep((requested - float(available)) / restore)

    if not dry_run:
        shop.last_synced_at = datetime.now(timezone.utc)
        await db.flush()

    return ImportResult(
        imported=imported,
        skipped=skipped,
        errors=errors,
        products_created=counters["products_created"],
        variants_created=counters["variants_created"],
        dry_run=dry_run,
        found=found,
        would_create=would_create,
        by_month=by_month,
        by_status=by_status,
        items_without_sku=items_without_sku,
        unbalanced=counters["unbalanced"],
    )


async def backfill_order_numbers(db: AsyncSession, shop: Shop) -> Dict[str, int]:
    """Fill `orders.order_number` for existing Shopify orders that lack it
    (ORDER-CARD-1 Part 1).

    Reuses the same page fetch + throttle backoff as `sync_shop_orders`: paginate
    the shop's Shopify orders, map numeric `id → name`, and UPDATE the matching
    rows. Cheaper than one query per order (~1 GraphQL call / 50 orders). Only
    touches `order_number` on rows that already exist — it never creates orders,
    never writes status/history, so the idempotent sync path is undisturbed.

    Idempotent: only rows with a NULL `order_number` are targeted, and paging
    stops as soon as names for all of them are found.
    """
    if shop.platform != ShopPlatform.SHOPIFY:
        return {"updated": 0, "examined": 0}
    if not shop.shopify_store_url or not shop.shopify_access_token_encrypted:
        return {"updated": 0, "examined": 0}

    # Only rows still missing a number (idempotent re-runs do near-zero work).
    result = await db.execute(
        select(Order.external_id).where(
            Order.shop_id == shop.id, Order.order_number.is_(None)
        )
    )
    remaining = {eid for eid in result.scalars().all() if eid}
    examined = len(remaining)
    if not remaining:
        return {"updated": 0, "examined": 0}

    token = decrypt_value(shop.shopify_access_token_encrypted)
    shop_url = str(shop.shopify_store_url)

    id_to_name: Dict[str, str] = {}
    after: Optional[str] = None
    while remaining:
        body = await _fetch_orders_page(
            shop_url, token, {"first": ORDERS_PAGE_SIZE, "after": after, "query": None}
        )
        conn = (body.get("data") or {}).get("orders") or {}
        edges = conn.get("edges") or []
        page_info = conn.get("pageInfo") or {}

        for edge in edges:
            node = (edge.get("node") if edge else None) or {}
            ext = _parse_shopify_gid(node.get("id"))
            name = node.get("name")
            if ext in remaining and name:
                id_to_name[ext] = name
                remaining.discard(ext)

        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")

        # Same proactive throttle backoff as sync_shop_orders.
        cost = (body.get("extensions") or {}).get("cost") or {}
        throttle = cost.get("throttleStatus") or {}
        available = throttle.get("currentlyAvailable")
        requested = float(cost.get("requestedQueryCost") or 0)
        restore = float(throttle.get("restoreRate") or DEFAULT_RESTORE_RATE) or DEFAULT_RESTORE_RATE
        if available is not None and float(available) < requested:
            await asyncio.sleep((requested - float(available)) / restore)

    updated = 0
    for ext, name in id_to_name.items():
        res = await db.execute(
            update(Order)
            .where(Order.external_id == ext, Order.shop_id == shop.id)
            .values(order_number=name)
        )
        updated += res.rowcount or 0
    await db.flush()

    logger.info(
        "Backfilled order_number for shop %s: updated=%d examined=%d",
        shop.id, updated, examined,
    )
    return {"updated": updated, "examined": examined}


# ORDER-SHIPPING-1: the report buckets months in the SHOP's timezone, because it
# is reconciled against Shopify analytics, which reports in that timezone.
# SHOPIFY-REFUNDS-followup-2 records what bucketing the same money in UTC costs:
# 2024-12 came out $39.99 wrong. `Europe/Kiev` is the spelling used everywhere
# else in this codebase (see the Nova Poshta service).
REPORT_TZ = ZoneInfo("Europe/Kiev")

# Cap on the worked examples carried in the report. Enough to diagnose a mapping
# bug by hand; not enough to turn a 677-order run into an unreadable payload.
MAX_REPORT_SAMPLES = 20


def _report_month(created_raw: Optional[str]) -> str:
    """Shopify `createdAt` (UTC ISO) → "YYYY-MM" in the reporting timezone."""
    if not created_raw:
        return "unknown"
    try:
        dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    return dt.astimezone(REPORT_TZ).strftime("%Y-%m")


async def backfill_shipping_breakdown(
    db: AsyncSession,
    shop: Shop,
    *,
    since: Optional[date] = None,
    until: Optional[date] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Fill `shipping_revenue` / `discount_total` / `tax_total` on orders that
    predate ORDER-SHIPPING-1, from Shopify (ORDER-SHIPPING-1).

    The order sync dedups on `(external_id, shop_id)` and never revisits an
    existing row, and the `orders/updated` webhook is a no-op on one — so setting
    the columns in the mappers prices new orders only. This is the path that
    reaches the ~677 already imported.

    Paging is `backfill_order_numbers`' — the same `ORDERS_QUERY`, page size,
    `_fetch_orders_page` throttle retries and proactive cost backoff — because it
    needs the same thing: walk the shop's orders once and UPDATE matching rows,
    at ~1 GraphQL call per 50 orders rather than one call per order. No by-id
    fetch is needed. It never creates orders and never writes status or history.

    FILL-ONLY, never refresh. A row is a write target only when all three columns
    are NULL, and that predicate is repeated in the UPDATE so a value written
    between the SELECT and the write is never clobbered. Re-running is therefore
    a strict no-op. Where Shopify now DISAGREES with a stored non-NULL value the
    run reports it and writes nothing — a post-hoc discount or a shipping edit in
    Shopify is real, but silently moving an order an operator has already
    reconciled is not this endpoint's call to make.

    The same reporting-only treatment catches `total_price` drift, which is the
    first actual measurement of BUG-4 (orders list reads a stale total). Also
    reported, never acted on.

    Windowing is by `Order.ordered_at`, NOT `COALESCE(shipped_at, ordered_at)` as
    in `backfill_platform_fees`: that one bounds what it re-prices in the P&L, so
    it uses the expression finance buckets by. This one is reconciled against
    Shopify's order feed, so it has to sit on the same clock as the Shopify-side
    `created_at` page filter, or the two ends of the comparison would select
    different orders.

    `dry_run` defaults TRUE. Everything is computed either way; only the UPDATE
    is skipped, so the report is what a real run would do.
    """
    empty: Dict[str, Any] = {
        "matched": 0,
        "found_in_shopify": 0,
        "missing_in_shopify": 0,
        "updated": 0,
        "shipping_total_by_currency": {},
        "discount_total_by_currency": {},
        "tax_total_by_currency": {},
        "by_month": {},
        "unbalanced": [],
        "drift": {
            "shipping_revenue": 0,
            "discount_total": 0,
            "tax_total": 0,
            "total_price": 0,
        },
        "drift_samples": [],
        "dry_run": dry_run,
    }
    if shop.platform != ShopPlatform.SHOPIFY:
        return empty
    if not shop.shopify_store_url or not shop.shopify_access_token_encrypted:
        return empty

    # Every order in the window, not just the write targets: drift is only
    # measurable against rows that already carry a value.
    conditions = [Order.shop_id == shop.id]
    if since is not None:
        conditions.append(cast(Order.ordered_at, Date) >= since)
    if until is not None:
        conditions.append(cast(Order.ordered_at, Date) <= until)

    result = await db.execute(
        select(
            Order.external_id,
            Order.currency,
            Order.total_price,
            Order.shipping_revenue,
            Order.discount_total,
            Order.tax_total,
        ).where(*conditions)
    )
    rows = {r.external_id: r for r in result.all() if r.external_id}
    if not rows:
        return empty

    token = decrypt_value(shop.shopify_access_token_encrypted)
    shop_url = str(shop.shopify_store_url)
    query_filter = _build_orders_query_filter(since, until)

    remaining = set(rows)
    to_write: Dict[str, Dict[str, Optional[Decimal]]] = {}
    shipping_by_currency: Dict[str, Decimal] = {}
    discount_by_currency: Dict[str, Decimal] = {}
    tax_by_currency: Dict[str, Decimal] = {}
    by_month: Dict[str, Dict[str, Any]] = {}
    unbalanced: list[dict] = []
    drift = {"shipping_revenue": 0, "discount_total": 0, "tax_total": 0, "total_price": 0}
    drift_samples: list[dict] = []
    found_in_shopify = 0

    after: Optional[str] = None
    while remaining:
        body = await _fetch_orders_page(
            shop_url,
            token,
            {"first": ORDERS_PAGE_SIZE, "after": after, "query": query_filter},
        )
        conn = (body.get("data") or {}).get("orders") or {}
        edges = conn.get("edges") or []
        page_info = conn.get("pageInfo") or {}

        for edge in edges:
            node = (edge.get("node") if edge else None) or {}
            ext = _parse_shopify_gid(node.get("id"))
            row = rows.get(ext)
            if row is None or ext not in remaining:
                continue
            remaining.discard(ext)
            found_in_shopify += 1

            breakdown = extract_money_breakdown(node)
            shopify_total = _to_decimal_or_none(
                ((node.get("totalPriceSet") or {}).get("shopMoney") or {}).get("amount")
            )

            imbalance = check_order_balance(
                total=shopify_total,
                shipping=breakdown["shipping_revenue"],
                discount=breakdown["discount_total"],
                tax=breakdown["tax_total"],
                subtotal=breakdown["subtotal"],
                items_gross=items_gross_from_node(node),
            )
            if imbalance and len(unbalanced) < MAX_REPORT_SAMPLES:
                unbalanced.append({
                    "order_number": node.get("name"),
                    "external_id": ext,
                    "reason": imbalance,
                })

            # Totals + per-month buckets cover every matched order, written or
            # not, so the figures reconcile against Shopify analytics for the
            # whole window rather than only the part this run happens to fill.
            currency = row.currency or "USD"
            month = _report_month(node.get("createdAt"))
            bucket = by_month.setdefault(
                month,
                {"orders": 0, "shipping": Decimal("0"), "discount": Decimal("0"), "tax": Decimal("0")},
            )
            bucket["orders"] += 1
            for key, agg, bkey in (
                ("shipping_revenue", shipping_by_currency, "shipping"),
                ("discount_total", discount_by_currency, "discount"),
                ("tax_total", tax_by_currency, "tax"),
            ):
                value = breakdown[key]
                if value is not None:
                    agg[currency] = agg.get(currency, Decimal("0")) + value
                    bucket[bkey] += value

            # Reported, never written (see docstring).
            if _to_decimal(row.total_price) != (shopify_total or Decimal("0")):
                drift["total_price"] += 1
                if len(drift_samples) < MAX_REPORT_SAMPLES:
                    drift_samples.append({
                        "order_number": node.get("name"),
                        "field": "total_price",
                        "stored": float(_to_decimal(row.total_price)),
                        "shopify": float(shopify_total or 0),
                    })

            is_target = (
                row.shipping_revenue is None
                and row.discount_total is None
                and row.tax_total is None
            )
            if is_target:
                to_write[ext] = breakdown
                continue

            for field in ("shipping_revenue", "discount_total", "tax_total"):
                stored = getattr(row, field)
                fresh = breakdown[field]
                if stored is None or fresh is None:
                    continue
                if _to_decimal(stored) != fresh:
                    drift[field] += 1
                    if len(drift_samples) < MAX_REPORT_SAMPLES:
                        drift_samples.append({
                            "order_number": node.get("name"),
                            "field": field,
                            "stored": float(_to_decimal(stored)),
                            "shopify": float(fresh),
                        })

        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")

        # Same proactive throttle backoff as sync_shop_orders.
        cost = (body.get("extensions") or {}).get("cost") or {}
        throttle = cost.get("throttleStatus") or {}
        available = throttle.get("currentlyAvailable")
        requested = float(cost.get("requestedQueryCost") or 0)
        restore = float(throttle.get("restoreRate") or DEFAULT_RESTORE_RATE) or DEFAULT_RESTORE_RATE
        if available is not None and float(available) < requested:
            await asyncio.sleep((requested - float(available)) / restore)

    updated = 0
    if not dry_run:
        for ext, breakdown in to_write.items():
            res = await db.execute(
                update(Order)
                # The all-NULL guard is repeated here, not just in the SELECT
                # above, so a value written between the two can never be
                # overwritten — and so a re-run stays a strict no-op.
                .where(
                    Order.external_id == ext,
                    Order.shop_id == shop.id,
                    Order.shipping_revenue.is_(None),
                    Order.discount_total.is_(None),
                    Order.tax_total.is_(None),
                )
                .values(
                    shipping_revenue=breakdown["shipping_revenue"],
                    discount_total=breakdown["discount_total"],
                    tax_total=breakdown["tax_total"],
                )
            )
            updated += res.rowcount or 0
        await db.flush()

    logger.info(
        "ORDER-SHIPPING-1 backfill for shop %s: matched=%d found=%d missing=%d "
        "targets=%d updated=%d unbalanced=%d dry_run=%s",
        shop.id, len(rows), found_in_shopify, len(remaining),
        len(to_write), updated, len(unbalanced), dry_run,
    )

    return {
        "matched": len(rows),
        "found_in_shopify": found_in_shopify,
        # In the DB but absent from Shopify's order feed — deleted upstream, or
        # outside the page filter. Their columns stay NULL, which reads correctly
        # as "unknown".
        "missing_in_shopify": len(remaining),
        "targets": len(to_write),
        "updated": updated,
        "shipping_total_by_currency": {c: float(v) for c, v in shipping_by_currency.items()},
        "discount_total_by_currency": {c: float(v) for c, v in discount_by_currency.items()},
        "tax_total_by_currency": {c: float(v) for c, v in tax_by_currency.items()},
        "by_month": {
            m: {
                "orders": b["orders"],
                "shipping": float(b["shipping"]),
                "discount": float(b["discount"]),
                "tax": float(b["tax"]),
            }
            for m, b in sorted(by_month.items())
        },
        "unbalanced": unbalanced,
        "drift": drift,
        "drift_samples": drift_samples,
        "dry_run": dry_run,
    }


async def sync_shop_refunds(
    db: AsyncSession,
    shop: Shop,
    *,
    updated_since: Optional[datetime] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Capture Shopify refunds as dated events and upsert them into `order_refunds`
    (SHOPIFY-REFUNDS, Model 2).

    Pages the shop's Shopify orders requesting each order's `refunds` list and upserts
    one row per Shopify refund, keyed by `shopify_refund_id`. Model 2: each refund is
    stored with its own `createdAt` as `refunded_at`, independent of the order's date, so
    finance nets it out in the period the refund occurred.

    One path, two modes:
      - Retro-fix / full backfill: `updated_since=None` → walks ALL orders (query=None).
      - Daily ongoing poll: `updated_since=<ts>` → filters `updated_at:>=…`, so refunds
        posted long after the order (which the order sync never revisits) are caught.

    Idempotent: existing `shopify_refund_id`s are skipped in memory and guarded at the DB
    by `uq_order_refund_shopify_id` (ON CONFLICT DO NOTHING), so re-runs write ~0 rows.
    `dry_run=True` computes the tally (incl. a per-month reconciliation) without writing.

    Reuses `_fetch_orders_page` (throttle backoff) and the `_bump_month` reconciliation
    shape (found / already_present / created) exactly like `sync_shop_orders`. Refunds are
    stored policy-free — the revenue-status filter is applied later, in finance.
    """
    zero = {
        "dry_run": dry_run,
        "refunds_found": 0,
        "inserted": 0,
        "already_present": 0,
        "skipped_no_order": 0,
        "by_month": {},
        "amount_by_currency": {},
    }
    if shop.platform != ShopPlatform.SHOPIFY:
        return zero
    if not shop.shopify_store_url or not shop.shopify_access_token_encrypted:
        return zero

    token = decrypt_value(shop.shopify_access_token_encrypted)
    shop_url = str(shop.shopify_store_url)
    query_filter = _build_refund_query_filter(updated_since)

    # Refund ids already stored for this shop — the in-memory idempotency guard (the DB
    # unique constraint is the race-safe backstop). Cheap: refund rows are few.
    existing_result = await db.execute(
        select(OrderRefund.shopify_refund_id)
        .join(Order, OrderRefund.order_id == Order.id)
        .where(Order.shop_id == shop.id)
    )
    existing_ids: set[str] = {rid for rid in existing_result.scalars().all() if rid}

    by_month: Dict[str, Dict[str, int]] = {}
    amount_by_currency: Dict[str, Decimal] = {}
    order_id_cache: Dict[str, Any] = {}  # external_id -> Order.id (UUID) or None
    refunds_found = 0
    inserted = 0
    already_present = 0
    skipped_no_order = 0

    after: Optional[str] = None
    while True:
        body = await _fetch_orders_page(
            shop_url,
            token,
            {"first": ORDERS_PAGE_SIZE, "after": after, "query": query_filter},
            REFUNDS_QUERY,
        )
        conn = (body.get("data") or {}).get("orders") or {}
        edges = conn.get("edges") or []
        page_info = conn.get("pageInfo") or {}

        for edge in edges:
            node = (edge.get("node") if edge else None) or {}
            refunds = node.get("refunds") or []
            if not refunds:
                continue
            ext = _parse_shopify_gid(node.get("id"))

            for refund in refunds:
                shopify_refund_id = _parse_shopify_gid(refund.get("id"))
                if not shopify_refund_id:
                    continue
                refunded_at = _parse_shopify_dt(refund.get("createdAt"))
                if refunded_at is None:
                    continue
                money = (refund.get("totalRefundedSet") or {}).get("shopMoney") or {}
                amount = _to_decimal(money.get("amount"))
                if amount <= 0:
                    continue  # restock-only / $0 refunds move no money — skip
                currency = money.get("currencyCode") or "USD"

                refunds_found += 1
                month = refunded_at.isoformat()[:7]
                _bump_month(by_month, month, "found")
                amount_by_currency[currency] = (
                    amount_by_currency.get(currency, Decimal("0")) + amount
                )

                if shopify_refund_id in existing_ids:
                    already_present += 1
                    _bump_month(by_month, month, "already_present")
                    continue

                # Resolve the local order lazily (only orders that actually have refunds).
                if ext not in order_id_cache:
                    res = await db.execute(
                        select(Order.id).where(
                            Order.external_id == ext, Order.shop_id == shop.id
                        )
                    )
                    order_id_cache[ext] = res.scalar_one_or_none()
                order_id = order_id_cache[ext]
                if order_id is None:
                    # Refund on an order we never imported — nothing to attach it to.
                    skipped_no_order += 1
                    continue

                existing_ids.add(shopify_refund_id)  # dedup within this same run too
                _bump_month(by_month, month, "created")
                if dry_run:
                    continue

                await db.execute(
                    pg_insert(OrderRefund)
                    .values(
                        order_id=order_id,
                        shopify_refund_id=shopify_refund_id,
                        refunded_at=refunded_at,
                        amount=amount,
                        currency=currency,
                    )
                    .on_conflict_do_nothing(constraint="uq_order_refund_shopify_id")
                )
                inserted += 1

        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")

        # Same proactive throttle backoff as sync_shop_orders / backfill_order_numbers.
        cost = (body.get("extensions") or {}).get("cost") or {}
        throttle = cost.get("throttleStatus") or {}
        available = throttle.get("currentlyAvailable")
        requested = float(cost.get("requestedQueryCost") or 0)
        restore = float(throttle.get("restoreRate") or DEFAULT_RESTORE_RATE) or DEFAULT_RESTORE_RATE
        if available is not None and float(available) < requested:
            await asyncio.sleep((requested - float(available)) / restore)

    if not dry_run:
        await db.flush()

    logger.info(
        "Refund sync for shop %s: found=%d inserted=%d already_present=%d "
        "skipped_no_order=%d dry_run=%s",
        shop.id, refunds_found, inserted, already_present, skipped_no_order, dry_run,
    )
    return {
        "dry_run": dry_run,
        "refunds_found": refunds_found,
        "inserted": inserted,
        "already_present": already_present,
        "skipped_no_order": skipped_no_order,
        "by_month": by_month,
        "amount_by_currency": {k: float(v) for k, v in amount_by_currency.items()},
    }
