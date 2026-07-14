"""
OrderHub CRM — Shopify Synchronization Service (GraphQL Edition)
Pulls orders from Shopify using GraphQL Admin API and upserts them into OrderHub.
"""

import httpx
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import logging
from typing import Any, Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.shop import Shop, ShopPlatform
from models.order import Order
from models.product import ProductVariant
from schemas.common import ImportResult
from schemas.order import OrderCreate, OrderItemCreate
from services.catalog_import import ensure_catalog_row, _weight_to_grams
from services.catalog_service import CatalogService
from services.encryption_service import decrypt_value
from services.order_service import create_order

SHOPIFY_API_VERSION = "2024-04"

ORDERS_QUERY = """
query GetRecentOrders($first: Int!) {
  orders(first: $first, sortKey: CREATED_AT, reverse: true) {
    edges {
      node {
        id
        name
        createdAt
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

async def sync_shop_orders(db: AsyncSession, shop: Shop, system_user) -> ImportResult:
    """Sync orders for a Shopify shop into the database, auto-creating Product/Variant catalog rows.

    Skip-on-existing semantics: orders dedup on `(external_id, shop_id)`; products dedup on
    `(shop_id, external_ref=shopify_product_id)`; variants dedup on shop-wide SKU. Re-syncs
    produce zero new rows when nothing changed upstream.
    """
    logger.info(f"Starting sync for shop: {shop.name} ({shop.id})")

    if shop.platform != ShopPlatform.SHOPIFY:
        logger.warning(f"Shop {shop.name} is not a Shopify shop, skipping.")
        return ImportResult(imported=0, skipped=0, errors=[])

    if not shop.shopify_store_url or not shop.shopify_access_token_encrypted:
        logger.warning(f"Shop {shop.name} is missing Shopify credentials.")
        return ImportResult(imported=0, skipped=0, errors=[])

    token = decrypt_value(shop.shopify_access_token_encrypted)

    try:
        data = await call_shopify_graphql(
            str(shop.shopify_store_url),
            token,
            ORDERS_QUERY,
            {"first": 50}
        )
    except Exception as e:
        logger.error(f"Failed to fetch orders from Shopify: {str(e)}")
        raise

    orders_edges = data.get("orders", {}).get("edges", [])
    logger.info(f"Found {len(orders_edges)} orders in Shopify response.")

    catalog_service = CatalogService(db)
    catalog_cache: Dict[str, Dict[str, Any]] = {}
    counters: Dict[str, int] = {"products_created": 0, "variants_created": 0}
    errors: list[dict] = []
    imported = 0
    skipped = 0

    for edge in orders_edges:
        node = edge.get("node", {}) or {}
        external_id = _parse_shopify_gid(node.get("id"))

        try:
            existing = await db.execute(
                select(Order).where(Order.external_id == external_id, Order.shop_id == shop.id)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            items_payload: list[OrderItemCreate] = []
            line_items_edges = ((node.get("lineItems") or {}).get("edges")) or []

            for li_edge in line_items_edges:
                li = (li_edge.get("node") if li_edge else None) or {}
                variant_node = li.get("variant")

                price_money = ((li.get("originalUnitPriceSet") or {}).get("shopMoney")) or {}
                price_amount = _to_decimal(price_money.get("amount"))
                line_currency = price_money.get("currencyCode") or "USD"

                variant_obj: Optional[ProductVariant] = None
                if variant_node and variant_node.get("product"):
                    ext_p = _parse_shopify_gid((variant_node.get("product") or {}).get("id"))
                    ext_v = _parse_shopify_gid(variant_node.get("id"))
                    raw_sku = (variant_node.get("sku") or "").strip()
                    sku = raw_sku or f"shopify-{ext_p}-{ext_v}"

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

            order_create_payload = OrderCreate(
                external_id=external_id,
                shop_id=shop.id,
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

            await create_order(db, order_create_payload, system_user)
            logger.info(f"Synced order: {order_create_payload.title}")
            imported += 1

        except Exception as e:
            logger.exception(f"Shopify sync failed for order {external_id}")
            errors.append({"external_id": external_id, "error": str(e)})

    shop.last_synced_at = datetime.now(timezone.utc)
    await db.flush()

    return ImportResult(
        imported=imported,
        skipped=skipped,
        errors=errors,
        products_created=counters["products_created"],
        variants_created=counters["variants_created"],
    )
