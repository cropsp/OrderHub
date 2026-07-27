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
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models.shop import Shop, ShopPlatform
from models.order import Order, OrderRefund, OrderStatus
from models.product import ProductVariant
from schemas.common import ImportResult
from schemas.order import OrderCreate, OrderItemCreate
from services.catalog_import import ensure_catalog_row, _weight_to_grams
from services.catalog_service import CatalogService
from services.encryption_service import decrypt_value
from services.order_service import create_order

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
    counters: Dict[str, int] = {"products_created": 0, "variants_created": 0}
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
