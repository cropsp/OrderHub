"""
OrderHub CRM — Imports Router
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from logger import get_logger
from models.user import User, UserRole
from models.shop import Shop, ShopPlatform
from schemas.common import ImportResult
from routers.dependencies import get_current_user, require_role
from services.etsy_parser import parse_etsy_csv

logger = get_logger("routers.imports")

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("/etsy", response_model=ImportResult)
async def import_etsy_orders(
    shop_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Import orders from an Etsy CSV export. Idempotent based on Sale ID."""
    
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
        
    result = await db.execute(select(Shop).where(Shop.id == shop_id, Shop.is_active == True))
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
        
    if shop.platform != ShopPlatform.ETSY:
        raise HTTPException(status_code=400, detail="Shop is not an Etsy shop")
        
    content = await file.read()
    
    try:
        import_result = await parse_etsy_csv(db, shop, content, current_user.id)
        await db.commit() # Commit the transaction here after successful parsing
        return import_result
    except Exception as e:
        await db.rollback()
        # CSV parse/validation errors carry actionable per-row context (e.g. "Row 5: missing 'Sale Date'");
        # surface them to the user verbatim. Internal traceback still goes to logs.
        logger.error(f"[IMPORTS] Etsy import failed for shop {shop_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to import: {str(e)}")
