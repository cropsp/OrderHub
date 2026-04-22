"""
OrderHub CRM — Shipping Router
Handles interactions with postal services (e.g. Nova Poshta).
"""

import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query

logger = logging.getLogger(__name__)
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
        logger.error(f"Nova Poshta Search Cities Error: {str(e)}")
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
        logger.error(f"Nova Poshta Get Warehouses Error: {str(e)}")
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
    
    # 1. Resolve Sender
    # Try to find a Sender counterparty for the shop
    senders = await np_client.get_counterparties("Sender")
    if not senders:
        raise HTTPException(status_code=400, detail="No Sender counterparty found for this API key")
    sender_ref = senders[0]["Ref"]
    
    # Get contact person for sender
    sender_contacts = await np_client.get_contact_persons(sender_ref)
    if not sender_contacts:
        raise HTTPException(status_code=400, detail="No contact person found for Sender counterparty")
    sender_contact_ref = sender_contacts[0]["Ref"]
    sender_phone = sender_contacts[0]["Phones"] # NP returns phone here

    # Get sender addresses (warehouses)
    sender_addresses = await np_client.get_counterparty_addresses(sender_ref)
    if not sender_addresses:
        # Fallback to Kyiv if no addresses found, but ideally we should have one
        sender_city_ref = shop.np_sender_city_ref or "8d5a980d-391c-11dd-90d9-001a92567626"
        sender_warehouse_ref = shop.np_sender_warehouse_ref or "1ec09d88-e1c2-11e3-8c4a-0050568002cf"
    else:
        # Use the first registered address
        sender_city_ref = sender_addresses[0]["CityRef"]
        sender_warehouse_ref = sender_addresses[0]["Ref"]

    # 2. Resolve Recipient
    # Separate names (NP expects Last/First/Middle)
    names = order.shipping_name.strip().split(" ", 2)
    last_name = names[0] if len(names) > 0 else "Отримувач"
    first_name = names[1] if len(names) > 1 else "Тест"
    middle_name = names[2] if len(names) > 2 else ""

    # Clean phone (remove +)
    clean_phone = order.shipping_phone.replace("+", "").replace(" ", "").replace("-", "")
    
    # Try to find recipient
    recipients = await np_client.get_counterparties("Recipient", clean_phone)
    if recipients:
        recipient_ref = recipients[0]["Ref"]
        # Get contact person
        recipient_contacts = await np_client.get_contact_persons(recipient_ref)
        if recipient_contacts:
            recipient_contact_ref = recipient_contacts[0]["Ref"]
        else:
            # Create contact person if missing (unlikely but possible)
            raise HTTPException(status_code=400, detail="Recipient found but has no contact persons")
    else:
        # Create new recipient counterparty
        recipient_data = await np_client.create_counterparty(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            phone=clean_phone
        )
        recipient_ref = recipient_data["Ref"]
        recipient_contact_ref = recipient_data["ContactPerson"]["data"][0]["Ref"]

    # 3. Build Payload
    from datetime import datetime
    payload = {
        "PayerType": "Sender",
        "PaymentMethod": "Cash",
        "DateTime": datetime.now().strftime("%d.%m.%Y"),
        "CargoType": "Parcel",
        "VolumeGeneral": "0.001",
        "Weight": str(weight),
        "ServiceType": "WarehouseWarehouse",
        "SeatsAmount": "1",
        "Description": description,
        "Cost": str(order.total_price),
        "CitySender": sender_city_ref,
        "Sender": sender_ref,
        "SenderAddress": sender_warehouse_ref,
        "ContactSender": sender_contact_ref,
        "SendersPhone": sender_phone,
        "CityRecipient": order.shipping_city_ref,
        "Recipient": recipient_ref,
        "RecipientAddress": order.shipping_warehouse_ref,
        "ContactRecipient": recipient_contact_ref,
        "RecipientsPhone": clean_phone,
    }
    
    logger.info(f"Creating NP TTN with payload: {payload}")
    
    try:
        ttn_data = await np_client.create_internet_document(payload)
        
        # Update order with TTN
        order.ttn_number = ttn_data.get("IntDocNumber")
        
        if order.status == OrderStatus.IN_PRODUCTION:
            await change_order_status(db, order, OrderStatus.SHIPPED, current_user, f"TTN created: {order.ttn_number}")
        
        await db.flush()
        return {"status": "success", "ttn": order.ttn_number}
        
    except Exception as e:
        logger.error(f"FAILED TO CREATE TTN: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"NP API Error: {str(e)}")
