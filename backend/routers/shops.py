"""
OrderHub CRM — Shops Router
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from logger import get_logger
from models.shop import Shop
from models.order import Order
from models.user import User, UserRole
from schemas.shop import (
    ShopBackfillRequest,
    ShopCreate,
    ShopUpdate,
    ShopResponse,
    ShopDetailResponse,
)
from routers.dependencies import assert_shop_access, get_current_user, require_role
from services.access_service import (
    get_shop_scope,
    propagate_new_shop_to_unrestricted_managers,
)
from services.partner_payout_service import find_settlements_overlapping_period
from services.shopify_sync import sync_shop_orders, backfill_order_numbers
from services.encryption_service import encrypt_value, decrypt_value
from services.phone_normalization import normalize_ua_sender_phone


logger = get_logger("routers.shops")

router = APIRouter(prefix="/api/shops", tags=["shops"])


@router.get("", response_model=list[ShopResponse])
async def list_shops(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List active shops the caller can access (USER-ACCESS-1, closes GAP B).

    Owner: all shops. Manager/designer: only granted shops. This is the source
    for the frontend sidebar / shop switcher, so scoping here filters those too.
    """
    query = (
        select(Shop)
        .where(Shop.is_active == True)
        .order_by(Shop.created_at.desc())
    )
    scope = await get_shop_scope(db, current_user)
    if not scope.is_unrestricted:
        query = query.where(Shop.id.in_(scope.shop_ids))

    result = await db.execute(query)
    shops = result.scalars().all()
    
    # Map to schema manually to set mask flags
    return [ShopResponse.model_validate({
        **s.__dict__,
        "has_shopify_token": bool(s.shopify_access_token_encrypted),
        "has_shopify_webhook_secret": bool(s.shopify_webhook_secret_encrypted),
        "has_np_token": bool(s.np_api_key_encrypted),
        "is_np_ready": bool(s.np_api_key_encrypted) and bool(s.np_sender_city_ref) and bool(s.np_sender_warehouse_ref),
    }) for s in shops]


@router.post("", response_model=ShopDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_shop(
    body: ShopCreate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new shop (owner only). Tokens are encrypted before saving."""
    shop = Shop(
        id=uuid.uuid4(),
        name=body.name,
        platform=body.platform,
        shopify_store_url=str(body.shopify_store_url) if body.shopify_store_url else None,
        np_sender_name=body.np_sender_name,
        np_sender_phone=normalize_ua_sender_phone(body.np_sender_phone),
        np_sender_city_ref=body.np_sender_city_ref,
        np_sender_warehouse_ref=body.np_sender_warehouse_ref,
        np_default_description=body.np_default_description,
        np_default_weight_kg=body.np_default_weight_kg,
        color=body.color,
        is_active=body.is_active,
    )
    
    if body.shopify_access_token:
        shop.shopify_access_token_encrypted = encrypt_value(body.shopify_access_token)
    if body.shopify_webhook_secret:
        shop.shopify_webhook_secret_encrypted = encrypt_value(body.shopify_webhook_secret)
    if body.np_api_key:
        shop.np_api_key_encrypted = encrypt_value(body.np_api_key)
        
    db.add(shop)
    await db.flush()
    await db.refresh(shop)
    # USER-ACCESS-1 (rule 1): grant the new shop to effectively-unrestricted
    # managers so today's "manager sees all shops" invariant holds for new shops,
    # without overriding a manager deliberately scoped to a subset.
    await propagate_new_shop_to_unrestricted_managers(db, shop.id, actor_id=current_user.id)
    await db.commit()

    resp = ShopDetailResponse.model_validate({
        **shop.__dict__,
        "has_shopify_token": bool(shop.shopify_access_token_encrypted),
        "has_shopify_webhook_secret": bool(shop.shopify_webhook_secret_encrypted),
        "has_np_token": bool(shop.np_api_key_encrypted),
        "is_np_ready": bool(shop.np_api_key_encrypted) and bool(shop.np_sender_city_ref) and bool(shop.np_sender_warehouse_ref),
        "order_count": 0
    })
    return resp


@router.get("/{shop_id}", response_model=ShopDetailResponse)
async def get_shop(
    shop_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get shop details and order count."""
    # USER-ACCESS-1 (GAP B): a non-owner may only see a granted shop.
    await assert_shop_access(db, shop_id, current_user)

    result = await db.execute(select(Shop).where(Shop.id == shop_id, Shop.is_active == True))
    shop = result.scalar_one_or_none()

    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")

    count_result = await db.execute(
        select(func.count()).select_from(Order).where(Order.shop_id == shop_id)
    )
    order_count = count_result.scalar() or 0
    
    resp = ShopDetailResponse.model_validate({
        **shop.__dict__,
        "has_shopify_token": bool(shop.shopify_access_token_encrypted),
        "has_shopify_webhook_secret": bool(shop.shopify_webhook_secret_encrypted),
        "has_np_token": bool(shop.np_api_key_encrypted),
        "is_np_ready": bool(shop.np_api_key_encrypted) and bool(shop.np_sender_city_ref) and bool(shop.np_sender_warehouse_ref),
        "order_count": order_count
    })
    return resp


@router.patch("/{shop_id}", response_model=ShopDetailResponse)
async def update_shop(
    shop_id: uuid.UUID,
    body: ShopUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """Update shop settings (owner only)."""
    result = await db.execute(select(Shop).where(Shop.id == shop_id))
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
        
    update_data = body.model_dump(exclude_unset=True, exclude={"shopify_access_token", "shopify_webhook_secret", "np_api_key"})

    # NP-FIX-3b: normalize sender phone on write (422 on unparseable input).
    if "np_sender_phone" in update_data:
        update_data["np_sender_phone"] = normalize_ua_sender_phone(update_data["np_sender_phone"])

    for key, value in update_data.items():
        if key == "shopify_store_url" and value is not None:
             setattr(shop, key, str(value))
        else:
             setattr(shop, key, value)
        
    if body.shopify_access_token is not None:
        if body.shopify_access_token == "":
             shop.shopify_access_token_encrypted = None
        else:
             shop.shopify_access_token_encrypted = encrypt_value(body.shopify_access_token)

    if body.shopify_webhook_secret is not None:
        if body.shopify_webhook_secret == "":
             shop.shopify_webhook_secret_encrypted = None
        else:
             shop.shopify_webhook_secret_encrypted = encrypt_value(body.shopify_webhook_secret)
             
    if body.np_api_key is not None:
        if body.np_api_key == "":
             shop.np_api_key_encrypted = None
        else:
             shop.np_api_key_encrypted = encrypt_value(body.np_api_key)
             
    await db.flush()
    await db.commit()
    
    return await get_shop(shop_id, current_user, db)


@router.delete("/{shop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shop(
    shop_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete a shop (owner only)."""
    result = await db.execute(select(Shop).where(Shop.id == shop_id))
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
        
    shop.is_active = False
    await db.flush()
    await db.commit()


@router.post("/{shop_id}/sync")
async def manual_sync_shop(
    shop_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a manual order sync for a specific shop."""
    # USER-ACCESS-1: a manager may only sync a shop they can access.
    await assert_shop_access(db, shop_id, current_user)

    result = await db.execute(select(Shop).where(Shop.id == shop_id, Shop.is_active == True))
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
        
    try:
        sync_result = await sync_shop_orders(db, shop, current_user)
        return {
            "status": "success",
            "synced_count": sync_result.imported,
            **sync_result.model_dump(),
        }
    except Exception as e:
        # Shopify import errors (auth failure, rate-limit, malformed payload) are actionable
        # for the operator triggering the sync; surface them. Traceback still goes to logs.
        logger.error(f"[SHOPS] Manual sync failed for shop {shop_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Manual sync failed: {str(e)}")


@router.post("/{shop_id}/backfill")
async def backfill_shop(
    shop_id: uuid.UUID,
    body: ShopBackfillRequest,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Bounded historical Shopify import for one shop (SHOPIFY-BACKFILL).

    Paginated + idempotent + dry-runnable. `dry_run=true` (the default) reports
    found / already-present / would-create per month WITHOUT writing — the first
    approval gate. Also returns two pre-import diagnostics:
      - suspicious_external_ids: existing orders in THIS shop whose external_id is
        not purely numeric (candidate hand-entries that won't dedup against the
        numeric backfill → double-count risk, Q1).
      - overlapping_settlements: immutable partner settlements whose period
        overlaps the window (their frozen amounts may now be under-settled, Q4).
    """
    # Same access rule as manual /sync: OWNER/MANAGER with access to this shop.
    await assert_shop_access(db, shop_id, current_user)

    result = await db.execute(select(Shop).where(Shop.id == shop_id, Shop.is_active == True))  # noqa: E712
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")

    # Q1 diagnostic: non-numeric external_ids in this shop (portable Python filter
    # rather than a DB-specific regex).
    existing_ids = (
        await db.execute(select(Order.external_id).where(Order.shop_id == shop_id))
    ).scalars().all()
    suspicious_external_ids = sorted(
        {eid for eid in existing_ids if eid and not eid.isdigit()}
    )

    # Q4 diagnostic: settlements overlapping the backfill window.
    overlapping_settlements = await find_settlements_overlapping_period(
        db, shop_id, body.since, body.until
    )

    try:
        result = await sync_shop_orders(
            db,
            shop,
            current_user,
            since=body.since,
            until=body.until,
            dry_run=body.dry_run,
            stop_on_existing=False,  # backfill walks the entire date range
        )
        # Real import commits via get_db on return; a raised HTTPException rolls it
        # back. Dry-run writes nothing, so the trailing get_db commit is a no-op.
        if body.dry_run:
            await db.rollback()  # belt-and-suspenders: dry-run must write nothing
    except Exception as e:
        logger.error(f"[SHOPS] Backfill failed for shop {shop_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Backfill failed: {str(e)}")

    return {
        "status": "success",
        **result.model_dump(),
        "suspicious_external_ids": suspicious_external_ids,
        "overlapping_settlements": overlapping_settlements,
    }


@router.post("/{shop_id}/backfill-order-numbers")
async def backfill_shop_order_numbers(
    shop_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Fill `order_number` (Shopify human order name) for existing orders in this
    shop that lack it (ORDER-CARD-1 Part 1).

    Idempotent and cheap: reuses the sync's paginated fetch to map id → name and
    only UPDATEs rows still missing a number. Never creates orders or touches
    status/history — the idempotent order-sync path is undisturbed. Non-Shopify
    shops are a no-op (updated=0).
    """
    # Same access rule as manual /sync + /backfill: OWNER/MANAGER with access.
    await assert_shop_access(db, shop_id, current_user)

    result = await db.execute(select(Shop).where(Shop.id == shop_id, Shop.is_active == True))  # noqa: E712
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")

    try:
        summary = await backfill_order_numbers(db, shop)
    except Exception as e:
        logger.error(f"[SHOPS] Order-number backfill failed for shop {shop_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order-number backfill failed: {str(e)}",
        )

    return {"status": "success", **summary}
