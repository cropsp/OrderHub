"""
OrderHub CRM — Webhooks Router
Handles real-time updates from Shopify and other platforms.
"""

import hmac
import hashlib
import base64
import json
import logging
import uuid
from decimal import Decimal
from fastapi import APIRouter, Request, Header, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from constants import SYSTEM_USER_ID
from database import get_db
from models.shop import Shop, ShopPlatform
from services.encryption_service import decrypt_value
from services.shopify_sync import (  # For fetching full details if needed
    call_shopify_graphql,
    check_order_balance,
    extract_money_breakdown_rest,
)
from schemas.order import OrderCreate
from services.order_service import compute_platform_fee, create_order, update_order
from models.order import Order
from models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

def verify_shopify_webhook(data: bytes, hmac_header: str, secret: str) -> bool:
    """Verify that the webhook actually came from Shopify."""
    hash = hmac.new(secret.encode('utf-8'), data, hashlib.sha256)
    expected_hmac = base64.b64encode(hash.digest()).decode('utf-8')
    return hmac.compare_digest(expected_hmac, hmac_header)

@router.post("/shopify/{shop_id}")
async def shopify_webhook(
    shop_id: uuid.UUID,
    request: Request,
    x_shopify_topic: str = Header(None),
    x_shopify_hmac_sha256: str = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """Handle incoming Shopify webhooks."""
    if not x_shopify_topic or not x_shopify_hmac_sha256:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing headers")

    # Get shop and decrypt secret
    result = await db.execute(select(Shop).where(Shop.id == shop_id))
    shop = result.scalar_one_or_none()
    
    if not shop or not shop.shopify_webhook_secret_encrypted:
        logger.error(f"Webhook received for unknown or unconfigured shop: {shop_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not configured for webhooks")

    secret = decrypt_value(shop.shopify_webhook_secret_encrypted)
    
    # Read raw body for HMAC verification
    body = await request.body()
    if not verify_shopify_webhook(body, x_shopify_hmac_sha256, secret):
        logger.warning(f"Invalid HMAC for shop {shop_id}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid HMAC")

    data = json.loads(body)
    external_id = str(data.get("id"))
    
    # System user for the audit trail (SEC-04). Installed by alembic
    # migration a1b2c3d4e5f6 — if missing, the deployment is misconfigured.
    user_result = await db.execute(select(User).where(User.id == SYSTEM_USER_ID))
    system_user = user_result.scalar_one_or_none()
    if system_user is None:
        logger.error("Cannot process webhook: system user %s not found", SYSTEM_USER_ID)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="System misconfigured")

    if x_shopify_topic == "orders/create" or x_shopify_topic == "orders/updated":
        logger.info(f"Processing Shopify webhook {x_shopify_topic} for order {external_id}")
        
        # Check if exists
        existing_res = await db.execute(
            select(Order).where(Order.external_id == external_id, Order.shop_id == shop_id)
        )
        existing = existing_res.scalar_one_or_none()
        
        # Parse data (similar to shopify_sync.py but from JSON payload)
        customer = data.get("customer") or {}
        shipping = data.get("shipping_address") or {}
        
        email = customer.get("email") or data.get("contact_email") or f"unknown_{external_id}@example.com"
        full_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip() or "Unknown Shopify Customer"
        
        payload = {
            "external_id": external_id,
            "shop_id": shop.id,
            "title": data.get("name", f"Order #{external_id}"),
            "total_price": float(data.get("total_price", 0)),
            "currency": data.get("currency", "USD"),
            # Webhook JSON uses ISO format
            "ordered_at": data.get("created_at"), 
            "shipping_name": shipping.get("name") or full_name,
            "shipping_phone": shipping.get("phone"),
            "shipping_street_1": shipping.get("address1"),
            "shipping_street_2": shipping.get("address2"),
            "shipping_city": shipping.get("city"),
            "shipping_state": shipping.get("province_code"),
            "shipping_zip": shipping.get("zip"),
            "shipping_country": shipping.get("country_code"),
            "customer_note": data.get("note"),
            "email": email,
            "full_name": full_name
        }

        if existing:
            # Update logic (minimal for now)
            # await update_order(db, existing.id, payload, system_user)
            logger.info(f"Order {external_id} already exists, skipping update for now.")
        else:
            # SHOP-FEE-1: same fee rule as the polling sync, so an order landing
            # here instead of there is priced identically. Webhook orders are
            # always created NEW, so there is no CANCELLED case to skip.
            platform_fee = compute_platform_fee(payload["total_price"], shop.fee_percent)

            # ORDER-SHIPPING-1: same three figures as the polling sync, read from
            # the REST payload's different field names (see
            # extract_money_breakdown_rest). Only Shopify's own invariant is
            # checkable here — this path creates no OrderItem rows, so there is
            # no line-item subtotal to reconcile against.
            breakdown = extract_money_breakdown_rest(data)
            imbalance = check_order_balance(
                total=Decimal(str(payload["total_price"])),
                shipping=breakdown["shipping_revenue"],
                discount=breakdown["discount_total"],
                tax=breakdown["tax_total"],
                subtotal=breakdown["subtotal"],
            )
            if imbalance:
                logger.warning(
                    "ORDER-SHIPPING-1 balance check failed (%s) for webhook order %s: "
                    "total=%s shipping=%s discount=%s tax=%s subtotal=%s",
                    imbalance, external_id, payload["total_price"],
                    breakdown["shipping_revenue"], breakdown["discount_total"],
                    breakdown["tax_total"], breakdown["subtotal"],
                )

            create_kwargs = {}
            if platform_fee is not None:
                # Literal "platform_fee: <amt>" token — see _FINANCIAL_COMMENT_RE
                # in order_service; this exact shape is what earns VIEW_COSTS
                # redaction in the order timeline.
                create_kwargs["history_comment"] = (
                    f"Created via Shopify webhook, "
                    f"platform_fee: {platform_fee} @ {shop.fee_percent}%"
                )
            await create_order(
                db,
                OrderCreate(**payload),
                system_user,
                platform_fee=platform_fee,
                shipping_revenue=breakdown["shipping_revenue"],
                discount_total=breakdown["discount_total"],
                tax_total=breakdown["tax_total"],
                **create_kwargs,
            )
            logger.info(f"Created new order {external_id} via webhook.")

    return {"status": "ok"}
