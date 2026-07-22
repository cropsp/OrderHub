"""
OrderHub CRM — Shipping Router
Handles interactions with postal services (e.g. Nova Poshta).
"""

import uuid
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from typing import List

from config import get_settings
from database import get_db
from models.attachment import Attachment, AttachmentType
from models.order import Order, OrderStatus
from models.shop import Shop
from models.stock_movement import StockMovementReason
from models.user import User, UserRole
from models.wb_parcel import WbParcel
from routers.dependencies import assert_order_access, require_role
from services import stock_service
from services.file_storage import save_order_bytes
from services.order_service import get_order_detail, change_order_status
from services.nova_poshta import NovaPoshtaClient, NovaPoshtaAPIError
from services.encryption_service import decrypt_value
from services.westernbid import (
    WesternBidClient,
    WesternBidLabelNotReady,
    find_candidate_parcels,
    load_westernbid_credentials,
    map_wb_item,
    normalize_wb_datetime,
    resolve_label_type,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/shipping", tags=["shipping"])

# NP-UX-2: NP returns these substrings (case-insensitive) when the TTN is already
# gone on their side — manual cabinet delete or earlier deletion. We treat them
# as effective success: clear local ttn_number anyway. Match is substring-based
# because NP varies the surrounding text ("Document already deleted 20451436…",
# "No document changed DeletionMark", "Document not found").
SOFT_SUCCESS_DELETE_PATTERNS = ("already deleted", "no document", "not found")


class CreateTTNRequest(BaseModel):
    weight: float | None = None
    description: str | None = None
    volume: float | None = None
    cash_on_delivery: bool = False
    cod_amount: float | None = None
    # Parcel dimensions in millimetres (frontend sends mm; handler converts to m³)
    length: float | None = None
    width: float | None = None
    height: float | None = None
    # Whether the user manually overrode the auto-calculated parcel values
    parcel_override: bool = False


@router.get("/cities")
async def search_cities(
    query: str = Query("", min_length=2),
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
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
        logger.error(f"[SHIPPING] Nova Poshta Search Cities Error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to communicate with shipping provider")

@router.get("/warehouses/{city_ref}")
async def get_warehouses(
    city_ref: str,
    query: str = Query(""),
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
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
        logger.error(f"[SHIPPING] Nova Poshta Get Warehouses Error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to communicate with shipping provider")


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

    # USER-ACCESS-1: a manager may only create a TTN for an accessible shop.
    await assert_order_access(db, order, current_user)

    if order.ttn_number:
        raise HTTPException(status_code=400, detail="Order already has a TTN")

    shop = order.shop
    if not shop or not shop.np_api_key_encrypted:
        raise HTTPException(status_code=400, detail="Shop does not have Nova Poshta configured")
        
    # Update parcel_override if provided
    if body.parcel_override != order.parcel_override:
        order.parcel_override = body.parcel_override
        
    # Ensure recipient data exists
    if not order.shipping_city or not order.shipping_name or not order.shipping_phone:
        raise HTTPException(status_code=400, detail="Order is missing required shipping information")

    if not order.shipping_city_ref or not order.shipping_warehouse_ref:
        raise HTTPException(
            status_code=400,
            detail="Order is missing Nova Poshta city or warehouse reference. "
                   "Please select them using the shipping editor."
        )

    if not shop.np_sender_city_ref or not shop.np_sender_warehouse_ref:
        raise HTTPException(
            status_code=400,
            detail="Shop's Nova Poshta sender warehouse is not configured. "
                   "Set it in Shops → Logistics (NP).",
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
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SHIPPING] NP sender resolution failed for shop {shop.id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to resolve sender with shipping provider")

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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SHIPPING] NP recipient resolution failed for order {order_id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to resolve recipient with shipping provider")

    # 3. Build Payload
    kyiv_tz = ZoneInfo("Europe/Kiev")
    
    # Calculate volume from dimensions if provided
    final_volume = body.volume
    if body.length and body.width and body.height:
        # L*W*H / 1,000,000,000 = m3
        calculated_volume = (body.length * body.width * body.height) / 1_000_000_000.0
        # Ensure at least 0.001 m3 for NP
        final_volume = max(calculated_volume, 0.0001)
        
    payload = {
        "PayerType": shop.np_default_payer_type or "Sender",
        "PaymentMethod": shop.np_default_payment_method or "Cash",
        "DateTime": datetime.now(tz=kyiv_tz).strftime("%d.%m.%Y"),
        "CargoType": "Parcel",
        "VolumeGeneral": f"{final_volume or shop.np_default_volume_m3 or 0.004:.4f}",
        "Weight": f"{body.weight or shop.np_default_weight_kg or 0.5:.3f}",
        "ServiceType": "WarehouseWarehouse",
        "SeatsAmount": "1",
        "Description": body.description or shop.np_default_description or f"Order #{order.external_id}",
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

        material_warnings: List[str] = []
        if order.status == OrderStatus.IN_PRODUCTION:
            # MAT-4: change_order_status fires the consumption hook on SHIPPED;
            # warnings propagate up so they ride the same toast surface as the
            # packaging warnings below.
            _, material_warnings = await change_order_status(
                db, order, OrderStatus.SHIPPED, current_user,
                f"TTN created: {order.ttn_number}",
            )

        # PKG-2: decrement packaging stock in the same transaction as the TTN write.
        # Guarded — no movement is recorded when the operator skipped packaging.
        packaging_warnings: List[str] = []
        if order.packaging_id is not None:
            packaging_warnings = await stock_service.apply_movement(
                db,
                box_id=order.packaging_id,
                delta=-1,
                reason=StockMovementReason.TTN_CREATE,
                order_id=order.id,
                user_id=current_user.id,
            )

        warnings = packaging_warnings + material_warnings

        await db.commit()
        await db.refresh(order)
        return {"status": "success", "ttn": order.ttn_number, "warnings": warnings}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"[SHIPPING] FAILED TO CREATE TTN: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to create shipping label")


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

    # USER-ACCESS-1: a manager may only delete a TTN for an accessible shop.
    await assert_order_access(db, order, current_user)

    if not order.ttn_number:
        raise HTTPException(status_code=400, detail="Order does not have a TTN")

    shop = order.shop
    if not shop or not shop.np_api_key_encrypted:
        raise HTTPException(status_code=400, detail="Shop does not have Nova Poshta configured")
        
    np_api_key = decrypt_value(shop.np_api_key_encrypted)
    np_client = NovaPoshtaClient(np_api_key)
    
    try:
        logger.info(f"[SHIPPING] Deleting TTN {order.ttn_number} for order {order_id}")

        soft_success = False
        try:
            await np_client.delete_internet_document(order.ttn_number)
        except NovaPoshtaAPIError as e:
            msg = str(e).lower()
            if any(pat in msg for pat in SOFT_SUCCESS_DELETE_PATTERNS):
                logger.info(
                    f"[SHIPPING] TTN {order.ttn_number} already gone on NP side ({e}); "
                    f"clearing local reference."
                )
                soft_success = True
            else:
                raise

        # Clear TTN from order
        old_ttn = order.ttn_number
        order.ttn_number = None

        # TTN-delete reverts SHIPPED → IN_PRODUCTION. Consumption is not undone
        # (no automatic reversal per design §4.3 / MAT-4 rule #10); warnings
        # from the transition are unused here. Comment text distinguishes
        # NP-confirmed delete from soft-success (already-gone) for audit.
        comment = (
            f"TTN already deleted on NP side, local ref cleared: {old_ttn}"
            if soft_success
            else f"TTN deleted: {old_ttn}"
        )
        await change_order_status(db, order, OrderStatus.IN_PRODUCTION, current_user, comment)

        # PKG-2: refund packaging stock in the same transaction as the TTN clear.
        # Fires on both real and soft success — semantically "no TTN exists for
        # this order anymore", per task.md rule #4.
        if order.packaging_id is not None:
            await stock_service.apply_movement(
                db,
                box_id=order.packaging_id,
                delta=+1,
                reason=StockMovementReason.TTN_DELETE,
                order_id=order.id,
                user_id=current_user.id,
            )

        await db.commit()
        await db.refresh(order)

        if soft_success:
            return {
                "status": "soft_success",
                "message": "TTN was already deleted on NP side; local reference cleared.",
            }
        return {"status": "success", "message": f"TTN {old_ttn} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"[SHIPPING] FAILED TO DELETE TTN: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to delete shipping label")


# ── WB-3: WesternBid thermal label print ───────────────────────────────────
#
# Read-only against WB (GetDocument retrieves an already-generated document — no
# CreateShipment, no money). WB exposes no order key on a parcel, so the manager
# confirms the order→parcel link from a name-matched candidate list; the picked
# parcel is mirrored + linked and its label PDF cached as an Attachment. See
# CLAUDE.md "WB-3" and services/westernbid.py.

# from_date margin before the order date for the live candidate search (rule 3).
WB_SEARCH_LOOKBACK_DAYS = 30


class WbLabelCandidate(BaseModel):
    shipment_id: uuid.UUID
    recipient_name: str | None = None
    recipient_postal_code: str | None = None
    recipient_country_code: str | None = None
    created_date: datetime | None = None
    shipping_type: str | None = None
    carrier_type: str | None = None


class WbLabelCandidatesResponse(BaseModel):
    # cached → a label PDF is already stored (print attachment_id); linked → parcel
    # already linked, no PDF yet (POST that shipment_id); candidates → manager must
    # pick; empty → nothing matched.
    status: str
    attachment_id: uuid.UUID | None = None
    file_name: str | None = None
    candidates: List[WbLabelCandidate] = []


class WbLabelConfirmRequest(BaseModel):
    shipment_id: uuid.UUID


class WbLabelResponse(BaseModel):
    # success → attachment_id is a printable PDF; unsupported → NovaPoshtaGlobal /
    # unknown carrier, message carries the cabinet-fallback text (rule 6).
    status: str
    attachment_id: uuid.UUID | None = None
    file_name: str | None = None
    message: str | None = None


def _wb_client_or_400(credentials: tuple[str, str] | None) -> WesternBidClient:
    if credentials is None:
        raise HTTPException(
            status_code=400,
            detail="WesternBid is not configured. Set the API credentials in Settings.",
        )
    api_key, login = credentials
    return WesternBidClient(api_key, login, get_settings().WESTERNBID_BASE_URL)


def _candidate_from_item(item: dict) -> WbLabelCandidate:
    return WbLabelCandidate(
        shipment_id=uuid.UUID(str(item["Id"])),
        recipient_name=item.get("RecipientName"),
        recipient_postal_code=item.get("RecipientPostalCode"),
        recipient_country_code=item.get("RecipientCountryCode"),
        created_date=normalize_wb_datetime(item.get("CreatedDate")),
        shipping_type=item.get("ShippingType"),
        carrier_type=item.get("CarrierType"),
    )


@router.get("/wb-label/{order_id}/candidates", response_model=WbLabelCandidatesResponse)
async def wb_label_candidates(
    order_id: uuid.UUID,
    broaden: bool = Query(False, description="Drop the country filter to widen the search"),
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Find WB parcel candidates for an order (manager-confirmed match, rule 3)."""
    order = await get_order_detail(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await assert_order_access(db, order, current_user)

    # Already linked → skip the picker. Cached PDF present → print it directly.
    linked = (
        await db.execute(select(WbParcel).where(WbParcel.order_id == order_id))
    ).scalars().first()
    if linked is not None:
        if linked.label_attachment_id is not None:
            att = await db.get(Attachment, linked.label_attachment_id)
            return WbLabelCandidatesResponse(
                status="cached",
                attachment_id=linked.label_attachment_id,
                file_name=att.file_name if att else None,
            )
        return WbLabelCandidatesResponse(
            status="linked",
            candidates=[
                WbLabelCandidate(
                    shipment_id=linked.shipment_id,
                    recipient_name=linked.recipient_name,
                    recipient_postal_code=linked.recipient_postal_code,
                    recipient_country_code=linked.recipient_country_code,
                    created_date=linked.wb_created_at,
                    shipping_type=linked.shipping_type,
                    carrier_type=linked.carrier_type,
                )
            ],
        )

    if not order.shipping_name:
        raise HTTPException(
            status_code=400,
            detail="Order has no recipient name to match against WesternBid.",
        )

    client = _wb_client_or_400(await load_westernbid_credentials(db))
    anchor = order.created_at or datetime.now(timezone.utc)
    from_date = anchor - timedelta(days=WB_SEARCH_LOOKBACK_DAYS)
    country = None if broaden else order.shipping_country
    try:
        parcels = await find_candidate_parcels(
            client,
            recipient_name=order.shipping_name,
            recipient_country_code=country,
            order_zip=order.shipping_zip,
            order_created_at=order.created_at,
            from_date=from_date,
        )
    except Exception as e:
        logger.error(
            f"[WB-LABEL] candidate search failed for order {order_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=502, detail="Failed to search WesternBid for parcels")

    candidates = [_candidate_from_item(p) for p in parcels if p.get("Id")]
    return WbLabelCandidatesResponse(
        status="candidates" if candidates else "empty",
        candidates=candidates,
    )


@router.post("/wb-label/{order_id}", response_model=WbLabelResponse)
async def wb_label_fetch(
    order_id: uuid.UUID,
    body: WbLabelConfirmRequest,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Confirm the order→parcel link, fetch the correct label, and cache it (rules 2, 5)."""
    order = await get_order_detail(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await assert_order_access(db, order, current_user)
    if not order.shipping_name:
        raise HTTPException(
            status_code=400,
            detail="Order has no recipient name to match against WesternBid.",
        )

    client = _wb_client_or_400(await load_westernbid_credentials(db))

    # Authoritative record: re-fetch by the order's recipient name and locate the
    # confirmed shipment. ShippingType (which label to fetch) is never trusted from
    # the client.
    anchor = order.created_at or datetime.now(timezone.utc)
    from_date = anchor - timedelta(days=WB_SEARCH_LOOKBACK_DAYS)
    try:
        parcels = await client.search_sent_parcels(order.shipping_name, None, from_date)
    except Exception as e:
        logger.error(
            f"[WB-LABEL] parcel re-fetch failed for order {order_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=502, detail="Failed to reach WesternBid")
    item = next(
        (p for p in parcels if str(p.get("Id")) == str(body.shipment_id)), None
    )
    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Selected WesternBid parcel not found. Refresh candidates and retry.",
        )

    # Concurrency (task reuse note): upsert the mirror row, then lock it. INSERT ON
    # CONFLICT DO NOTHING makes the first-fetch race safe; FOR UPDATE serialises the
    # fetch so two clicks can't double-call WB or orphan an Attachment.
    await db.execute(
        pg_insert(WbParcel)
        .values(shipment_id=body.shipment_id, **map_wb_item(item))
        .on_conflict_do_nothing(index_elements=["shipment_id"])
    )
    parcel = (
        await db.execute(
            select(WbParcel)
            .where(WbParcel.shipment_id == body.shipment_id)
            .with_for_update()
        )
    ).scalar_one()

    # Re-check after the lock: a concurrent request may have just cached it.
    if parcel.label_attachment_id is not None:
        att = await db.get(Attachment, parcel.label_attachment_id)
        if att is not None:
            parcel.order_id = order_id
            await db.commit()
            return WbLabelResponse(
                status="success", attachment_id=att.id, file_name=att.file_name
            )

    parcel.order_id = order_id

    label_type = resolve_label_type(parcel.shipping_type)
    if label_type is None:
        # NovaPoshtaGlobal / unknown carrier — do NOT fetch a wrong document (rule 6).
        await db.commit()
        return WbLabelResponse(
            status="unsupported",
            message=(
                f"No API thermal label for carrier '{parcel.shipping_type}'. "
                "Print it from the WesternBid cabinet documents page."
            ),
        )

    document_type, paper_size = label_type
    try:
        pdf_bytes = await client.get_document(body.shipment_id, document_type, paper_size)
    except WesternBidLabelNotReady:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The label is not ready yet on WesternBid. Try again shortly.",
        )
    except Exception as e:
        await db.rollback()
        logger.error(
            f"[WB-LABEL] GetDocument failed for order {order_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=502, detail="Failed to fetch the label from WesternBid")

    rel_path, size = await save_order_bytes(pdf_bytes, order_id, "pdf")
    attachment = Attachment(
        id=uuid.uuid4(),
        order_id=order_id,
        uploaded_by_id=current_user.id,
        file_name=f"wb-label-{order.external_id or order_id}.pdf",
        file_path=rel_path,
        file_size=size,
        mime_type="application/pdf",
        attachment_type=AttachmentType.OTHER,
    )
    db.add(attachment)
    await db.flush()
    parcel.label_attachment_id = attachment.id
    order.ttn_printed = True  # WB-3 Q5: mark on produce/serve (backend).
    await db.commit()
    return WbLabelResponse(
        status="success", attachment_id=attachment.id, file_name=attachment.file_name
    )
