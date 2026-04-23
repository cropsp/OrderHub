"""
OrderHub CRM — Shipping Router
Handles interactions with postal services (e.g. Nova Poshta).
"""

import uuid
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from database import get_db
from models.order import Order, OrderStatus
from models.shop import Shop
from models.user import User, UserRole
from routers.dependencies import get_current_user, require_role
from services.order_service import get_order_detail, change_order_status
from services.nova_poshta import NovaPoshtaClient
from services.encryption_service import decrypt_value
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shipping", tags=["shipping"])


class CreateTTNRequest(BaseModel):
    weight: float | None = None
    description: str | None = None
    volume: float | None = None
    cash_on_delivery: bool = False
    cod_amount: float | None = None


@router.get("/cities")
async def search_cities(
    query: str = Query("", min_length=2),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search for cities in Nova Poshta."""
    # Find any shop with NP key to use for the request
    stmt = select(Shop).where(Shop.np_api_key_encrypted != None).limit(1)
    result = await db.execute(stmt)
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=400, detail="No shop with Nova Poshta API key found")
        
    np_api_key = decrypt_value(shop.np_api_key_encrypted)
    np_client = NovaPoshtaClient(np_api_key)
    try:
        cities = await np_client.get_cities(query)
        return cities
    except Exception as e:
        logger.error(f"[SHIPPING] Nova Poshta Search Cities Error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/warehouses/{city_ref}")
async def get_warehouses(
    city_ref: str,
    query: str = Query(""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get warehouses in a city."""
    stmt = select(Shop).where(Shop.np_api_key_encrypted != None).limit(1)
    result = await db.execute(stmt)
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=400, detail="No shop with Nova Poshta API key found")
        
    try:
        np_api_key = decrypt_value(shop.np_api_key_encrypted)
        np_client = NovaPoshtaClient(np_api_key)
        warehouses = await np_client.get_warehouses(city_ref, query)
        return warehouses
    except Exception as e:
        logger.error(f"[SHIPPING] Nova Poshta Get Warehouses Error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


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
        
    # Ensure recipient data exists
    if not order.shipping_city or not order.shipping_name or not order.shipping_phone:
        raise HTTPException(status_code=400, detail="Order is missing required shipping information")

    if not order.shipping_city_ref or not order.shipping_warehouse_ref:
        raise HTTPException(
            status_code=400, 
            detail="Order is missing Nova Poshta city or warehouse reference. "
                   "Please select them using the shipping editor."
        )

    np_api_key = decrypt_value(shop.np_api_key_encrypted)
    np_client = NovaPoshtaClient(np_api_key)
    
    # 1. Resolve Sender
    try:
        if shop.np_sender_ref and shop.np_sender_contact_ref:
            logger.info(f"[SHIPPING] Using cached sender refs for shop {shop.id}")
            sender_ref = shop.np_sender_ref
            sender_contact_ref = shop.np_sender_contact_ref
        else:
            logger.info(f"[SHIPPING] Resolving sender refs from NP API for shop {shop.id}")
            senders = await np_client.get_counterparties("Sender")
            if not senders:
                raise HTTPException(status_code=400, detail="No Sender counterparty found for this API key")
            sender_ref = senders[0]["Ref"]
            
            sender_contacts = await np_client.get_contact_persons(sender_ref)
            if not sender_contacts:
                raise HTTPException(status_code=400, detail="No contact person found for Sender counterparty")
            sender_contact_ref = sender_contacts[0]["Ref"]
            
            # Cache the refs
            shop.np_sender_ref = sender_ref
            shop.np_sender_contact_ref = sender_contact_ref
            # Commit immediately so refs are cached even if later steps fail
            await db.commit()
            await db.refresh(shop)
            # Re-fetch order and shop because commit/refresh might have expired them in some session configs
            # (though with selectin loading it should be fine, but let's be careful)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NP API Error (Sender): {str(e)}")

    # 2. Resolve Recipient
    # Separate names (NP expects Last/First/Middle)
    names = order.shipping_name.strip().split(" ", 2)
    last_name = names[0] if len(names) > 0 else "Отримувач"
    first_name = names[1] if len(names) > 1 else "Тест"
    middle_name = names[2] if len(names) > 2 else ""

    # Clean phone (remove everything except digits, ensure 380 format)
    clean_phone = "".join(filter(str.isdigit, order.shipping_phone))
    if clean_phone.startswith("0"):
        clean_phone = "38" + clean_phone
    elif not clean_phone.startswith("38"):
        # Very basic fallback, NP will validate further
        pass
    
    try:
        # Try to find recipient
        recipients = await np_client.get_counterparties("Recipient", clean_phone)
        if recipients:
            recipient_ref = recipients[0]["Ref"]
            recipient_contacts = await np_client.get_contact_persons(recipient_ref)
            if recipient_contacts:
                recipient_contact_ref = recipient_contacts[0]["Ref"]
            else:
                raise HTTPException(status_code=400, detail="Recipient found but has no contact persons")
        else:
            # Create new recipient
            recipient_data = await np_client.create_counterparty(
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                phone=clean_phone
            )
            recipient_ref = recipient_data["Ref"]
            recipient_contact_ref = recipient_data["ContactPerson"]["data"][0]["Ref"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NP API Error (Recipient): {str(e)}")

    # 3. Build Payload
    kyiv_tz = ZoneInfo("Europe/Kiev")
    payload = {
        "PayerType": shop.np_default_payer_type or "Sender",
        "PaymentMethod": shop.np_default_payment_method or "Cash",
        "DateTime": datetime.now(tz=kyiv_tz).strftime("%d.%m.%Y"),
        "CargoType": "Parcel",
        "VolumeGeneral": str(body.volume or shop.np_default_volume_m3 or 0.004),
        "Weight": str(body.weight or shop.np_default_weight_kg or 0.5),
        "ServiceType": "WarehouseWarehouse",
        "SeatsAmount": "1",
        "Description": body.description or shop.np_default_description or f"Order #{order.order_number}",
        "Cost": str(int(order.total_price)),
        "CitySender": shop.np_sender_city_ref,
        "Sender": sender_ref,
        "SenderAddress": shop.np_sender_warehouse_ref,
        "ContactSender": sender_contact_ref,
        "SendersPhone": shop.np_sender_phone,
        "CityRecipient": order.shipping_city_ref,
        "Recipient": recipient_ref,
        "RecipientAddress": order.shipping_warehouse_ref,
        "ContactRecipient": recipient_contact_ref,
        "RecipientsPhone": clean_phone,
    }

    # Add COD if requested
    if body.cash_on_delivery:
        cod_val = body.cod_amount or order.total_price
        payload["BackwardDeliveryData"] = [{
            "PayerType": "Recipient",
            "CargoType": "Money",
            "RedeliveryString": str(int(cod_val))
        }]
    
    logger.info(f"Creating NP TTN with payload: {payload}")
    
    try:
        ttn_data = await np_client.create_internet_document(payload)
        
        # Update order with TTN
        order.ttn_number = ttn_data.get("IntDocNumber")
        
        if order.status == OrderStatus.IN_PRODUCTION:
            await change_order_status(db, order, OrderStatus.SHIPPED, current_user, f"TTN created: {order.ttn_number}")
        
        await db.commit()
        await db.refresh(order)
        return {"status": "success", "ttn": order.ttn_number}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"[SHIPPING] FAILED TO CREATE TTN: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"NP API Error: {str(e)}")


@router.delete("/np-ttn/{order_id}")
async def delete_np_ttn(
    order_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Delete the Nova Poshta TTN (waybill) for the specified order and clear it from the database."""
    order = await get_order_detail(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if not order.ttn_number:
        raise HTTPException(status_code=400, detail="Order does not have a TTN")

    shop = order.shop
    if not shop or not shop.np_api_key_encrypted:
        raise HTTPException(status_code=400, detail="Shop does not have Nova Poshta configured")
        
    np_api_key = decrypt_value(shop.np_api_key_encrypted)
    np_client = NovaPoshtaClient(np_api_key)
    
    try:
        logger.info(f"[SHIPPING] Deleting TTN {order.ttn_number} for order {order_id}")
        
        await np_client.delete_internet_document(order.ttn_number)
        
        # Clear TTN from order
        old_ttn = order.ttn_number
        order.ttn_number = None
        
        await change_order_status(db, order, OrderStatus.IN_PRODUCTION, current_user, f"TTN deleted: {old_ttn}")
        
        await db.commit()
        await db.refresh(order)
        return {"status": "success", "message": f"TTN {old_ttn} deleted"}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"[SHIPPING] FAILED TO DELETE TTN: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"NP API Error: {str(e)}")
