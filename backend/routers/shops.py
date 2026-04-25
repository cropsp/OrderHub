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
from schemas.shop import ShopCreate, ShopUpdate, ShopResponse, ShopDetailResponse
from routers.dependencies import get_current_user, require_role
from services.shopify_sync import sync_shop_orders
from services.encryption_service import encrypt_value, decrypt_value


logger = get_logger("routers.shops")

router = APIRouter(prefix="/api/shops", tags=["shops"])


@router.get("", response_model=list[ShopResponse])
async def list_shops(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active shops. All authenticated users can see this."""
    result = await db.execute(
        select(Shop)
        .where(Shop.is_active == True)
        .order_by(Shop.created_at.desc())
    )
    shops = result.scalars().all()
    
    # Map to schema manually to set mask flags
    return [ShopResponse.model_validate({
        **s.__dict__,
        "has_shopify_token": bool(s.shopify_access_token_encrypted),
        "has_shopify_webhook_secret": bool(s.shopify_webhook_secret_encrypted),
        "has_np_token": bool(s.np_api_key_encrypted)
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
        np_sender_phone=body.np_sender_phone,
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
    await db.commit()
    
    resp = ShopDetailResponse.model_validate({
        **shop.__dict__,
        "has_shopify_token": bool(shop.shopify_access_token_encrypted),
        "has_shopify_webhook_secret": bool(shop.shopify_webhook_secret_encrypted),
        "has_np_token": bool(shop.np_api_key_encrypted),
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
    result = await db.execute(select(Shop).where(Shop.id == shop_id, Shop.is_active == True))
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
        
    try:
        count = await sync_shop_orders(db, shop, current_user)
        return {"status": "success", "synced_count": count}
    except Exception as e:
        logger.error(f"[SHOPS] Manual sync failed for shop {shop_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Manual sync failed")
