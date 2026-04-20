"""
OrderHub CRM — Shopify Synchronization Service
Pulls orders from Shopify and upserts them into OrderHub.
"""

import httpx
from datetime import datetime, timezone
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from models.shop import Shop, ShopPlatform
from models.order import Order
from schemas.order import OrderCreate
from services.order_service import create_order
from services.encryption_service import decrypt_value

async def fetch_shopify_orders(shop_url: str, access_token: str, limit: int = 50) -> list[dict]:
    """Fetch recent orders from Shopify Admin API."""
    url = f"{shop_url.rstrip('/')}/admin/api/2024-01/orders.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }
    params = {"status": "any", "limit": limit}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json().get("orders", [])
        except httpx.HTTPStatusError as e:
            # Handle specific API errors
            raise Exception(f"Shopify Sync Error: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Shopify Sync failed: {str(e)}")

async def sync_shop_orders(db: AsyncSession, shop: Shop, system_user):
    """Sync orders for a specific shop into the database."""
    if shop.platform != ShopPlatform.SHOPIFY:
        return 0
        
    if not shop.shopify_store_url or not shop.shopify_access_token_encrypted:
        return 0

    token = decrypt_value(shop.shopify_access_token_encrypted)
    orders_data = await fetch_shopify_orders(str(shop.shopify_store_url), token)
    
    synced_count = 0
    for s_order in orders_data:
        # Check if order already exists
        external_id = str(s_order["id"])
        
        existing = await db.execute(
            select(Order).where(Order.external_id == external_id, Order.shop_id == shop.id)
        )
        if existing.scalar_one_or_none():
            continue  # Skip existing for now (could update in the future)
            
        # Parse customer
        customer_data = s_order.get("customer", {})
        email = customer_data.get("email") or s_order.get("contact_email") or f"unknown_{external_id}@example.com"
        first_name = customer_data.get("first_name", "")
        last_name = customer_data.get("last_name", "")
        full_name = f"{first_name} {last_name}".strip() or "Unknown Shopify Customer"
        
        # Parse shipping address
        shipping_address = s_order.get("shipping_address", {})
        
        # Try finding a name from shipping, or default back to customer
        shipping_name = shipping_address.get("name") or full_name
        
        order_create_payload = OrderCreate(
            external_id=external_id,
            shop_id=shop.id,
            title=s_order.get("name", f"Order #{external_id}"),
            total_price=float(s_order.get("total_price", 0)),
            currency=s_order.get("currency", "USD"),
            ordered_at=datetime.fromisoformat(s_order["created_at"]) if "created_at" in s_order else datetime.now(timezone.utc),
            
            # Shipping data
            shipping_name=shipping_name,
            shipping_phone=shipping_address.get("phone"),
            shipping_street_1=shipping_address.get("address1"),
            shipping_street_2=shipping_address.get("address2"),
            shipping_city=shipping_address.get("city"),
            shipping_state=shipping_address.get("province"),
            shipping_zip=shipping_address.get("zip"),
            shipping_country=shipping_address.get("country_code"),
            
            # Additional info
            customer_note=s_order.get("note"),
            
            # Needed for custom customer creation if missing
            email=email,
            full_name=full_name
        )
        
        await create_order(db, order_create_payload, system_user)
        synced_count += 1
        
    # Update last_synced_at
    shop.last_synced_at = datetime.now(timezone.utc)
    await db.flush()
    
    return synced_count
