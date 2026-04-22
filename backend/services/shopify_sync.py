"""
OrderHub CRM — Shopify Synchronization Service (GraphQL Edition)
Pulls orders from Shopify using GraphQL Admin API and upserts them into OrderHub.
"""

import httpx
import json
from datetime import datetime, timezone
import uuid
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from models.shop import Shop, ShopPlatform
from models.order import Order
from schemas.order import OrderCreate
from services.order_service import create_order
from services.encryption_service import decrypt_value

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
      }
    }
  }
}
"""

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

async def sync_shop_orders(db: AsyncSession, shop: Shop, system_user):
    """Sync orders for a specific shop into the database using GraphQL."""
    logger.info(f"Starting sync for shop: {shop.name} ({shop.id})")
    
    if shop.platform != ShopPlatform.SHOPIFY:
        logger.warning(f"Shop {shop.name} is not a Shopify shop, skipping.")
        return 0
        
    if not shop.shopify_store_url or not shop.shopify_access_token_encrypted:
        logger.warning(f"Shop {shop.name} is missing Shopify credentials.")
        return 0

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
    
    synced_count = 0
    
    for edge in orders_edges:
        node = edge.get("node", {})
        # Shopify GraphQL IDs look like "gid://shopify/Order/123456789"
        # We extract the numeric part for external_id to stay consistent with REST if needed,
        # or just use the full string. Let's use the numeric part.
        full_id = node.get("id", "")
        external_id = full_id.split("/")[-1] if "/" in full_id else full_id
        
        # Check if order already exists
        existing = await db.execute(
            select(Order).where(Order.external_id == external_id, Order.shop_id == shop.id)
        )
        if existing.scalar_one_or_none():
            continue
            
        # Parse customer
        customer = node.get("customer") or {}
        email = customer.get("email") or f"unknown_{external_id}@example.com"
        first_name = customer.get('firstName', '') or ''
        last_name = customer.get('lastName', '') or ''
        full_name = f"{first_name} {last_name}".strip() or "Unknown Shopify Customer"
        
        # Parse shipping address
        shipping = node.get("shippingAddress") or {}
        
        # Parse money
        money = node.get("totalPriceSet", {}).get("shopMoney", {})
        
        order_create_payload = OrderCreate(
            external_id=external_id,
            shop_id=shop.id,
            title=node.get("name", f"Order #{external_id}"),
            total_price=float(money.get("amount", 0)),
            currency=money.get("currencyCode", "USD"),
            ordered_at=datetime.fromisoformat(node["createdAt"].replace("Z", "+00:00")),
            
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
            full_name=full_name
        )
        
        await create_order(db, order_create_payload, system_user)
        logger.info(f"Synced order: {order_create_payload.title}")
        synced_count += 1
        
    # Update last_synced_at
    shop.last_synced_at = datetime.now(timezone.utc)
    await db.flush()
    
    return synced_count
