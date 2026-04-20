"""
OrderHub CRM — Shipping Router
Handles interactions with postal services (e.g. Nova Poshta).
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models.order import Order, OrderStatus
from models.shop import Shop
from models.user import User, UserRole
from routers.dependencies import get_current_user, require_role
from services.order_service import get_order_detail, change_order_status
from services.nova_poshta import NovaPoshtaClient, build_ttn_payload
from services.encryption_service import decrypt_value
from pydantic import BaseModel


router = APIRouter(prefix="/api/shipping", tags=["shipping"])


class CreateTTNRequest(BaseModel):
    weight: float | None = None
    description: str | None = None


@router.post("/np-ttn/{order_id}")
async def create_np_ttn(
    order_id: uuid.UUID,
    body: CreateTTNRequest,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Generate a Nova Poshta TTN (waybill) for the specified order."""
    order = await get_order_detail(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if order.ttn_number:
        raise HTTPException(status_code=400, detail="Order already has a TTN")

    shop = order.shop
    if not shop or not shop.np_api_key_encrypted:
        raise HTTPException(status_code=400, detail="Shop does not have Nova Poshta configured")
        
    np_api_key = decrypt_value(shop.np_api_key_encrypted)
    np_client = NovaPoshtaClient(np_api_key)
    
    # Use provided values, fallback to shop defaults, then hardcoded fallbacks
    weight = body.weight or shop.np_default_weight_kg or 0.5
    description = body.description or shop.np_default_description or order.title
    
    # Ensure recipient data exists
    if not order.shipping_city or not order.shipping_name or not order.shipping_phone:
        raise HTTPException(status_code=400, detail="Order is missing required shipping information")

    # In a full flow, you would lookup CityRef and WarehouseRef dynamically here
    # For MVP S6-2, we assume they are already known or we do a quick lookup
    # Because NP requires Ref UUIDs, this requires fetching them just-in-time or storing them.
    # We will simulate a TTN payload (NP API will likely reject fake Refs).
    
    # We use hardcoded refs for testing if missing
    SENDER_CITY_REF = shop.np_sender_city_ref or "8d5a980d-391c-11dd-90d9-001a92567626" # Kyiv
    SENDER_WAREHOUSE_REF = shop.np_sender_warehouse_ref or "1ec09d88-e1c2-11e3-8c4a-0050568002cf" # WH 1
    
    payload = build_ttn_payload(
        sender_city_ref=SENDER_CITY_REF,
        sender_warehouse_ref=SENDER_WAREHOUSE_REF,
        sender_phone=shop.np_sender_phone or "+380990000000",
        sender_name=shop.np_sender_name or "Shop Sender Name",
        recipient_city_ref="8d5a980d-391c-11dd-90d9-001a92567626", # Target city ref (mocked)
        recipient_warehouse_ref="1ec09d88-e1c2-11e3-8c4a-0050568002cf", # Target WH ref (mocked)
        recipient_phone=order.shipping_phone,
        recipient_name=order.shipping_name,
        weight=weight,
        description=description,
        cost=order.total_price  # Value for insurance
    )
    
    try:
        ttn_data = await np_client.create_internet_document(payload)
        
        # Update order with TTN
        order.ttn_number = ttn_data.get("IntDocNumber")
        
        # Optionally move status to SHIPPED if it was IN_PRODUCTION
        if order.status == OrderStatus.IN_PRODUCTION:
            await change_order_status(db, order, OrderStatus.SHIPPED, current_user, f"TTN created: {order.ttn_number}")
        
        await db.flush()
        return {"status": "success", "ttn": order.ttn_number}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"NP API Error: {str(e)}")
