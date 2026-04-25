import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.shop import ShopPlatform
from models.user import UserRole
from routers.dependencies import get_current_user, get_shop_for_user, require_platform, require_role
from schemas.product import ProductCreate, ProductRead, ProductUpdate, ProductVariantRead
from schemas.import_preview import ImportPreviewResponse, ImportConfirmRequest
from services.catalog_service import CatalogService
from services.import_service import ImportService


router = APIRouter(prefix="/api", tags=["Products"])


@router.get("/shops/{shop_id}/products", response_model=List[ProductRead])
async def list_products(
    shop_id: uuid.UUID,
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db),
    shop=Depends(require_platform(ShopPlatform.MANUAL.value))
):
    """List all products for a manual shop."""
    service = CatalogService(db)
    return await service.get_products(shop_id, is_active=is_active)


@router.post("/shops/{shop_id}/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    shop_id: uuid.UUID,
    schema: ProductCreate,
    db: AsyncSession = Depends(get_db),
    shop=Depends(require_platform(ShopPlatform.MANUAL.value))
):
    """Create a new product with variants."""
    service = CatalogService(db)
    
    # Check SKU uniqueness for all new variants
    for variant in schema.variants:
        if await service.is_sku_taken(shop_id, variant.sku):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SKU '{variant.sku}' is already taken in this shop"
            )
            
    return await service.create_product(shop_id, schema)


@router.get("/products/{id}", response_model=ProductRead)
async def get_product(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get product details."""
    service = CatalogService(db)
    product = await service.get_product(id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/products/{id}", response_model=ProductRead)
async def update_product(
    id: uuid.UUID,
    schema: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER))
):
    """Update product details."""
    service = CatalogService(db)
    product = await service.update_product(id, schema)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.delete("/products/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER))
):
    """Soft-delete a product."""
    service = CatalogService(db)
    await service.soft_delete_product(id)


# --- Bulk CSV Import (Two-step) ---

@router.post("/shops/{shop_id}/products/bulk-csv/preview", response_model=ImportPreviewResponse)
async def preview_products_import(
    shop_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    shop=Depends(require_platform(ShopPlatform.MANUAL.value))
):
    """Validate CSV and return a preview of products to be imported."""
    content = await file.read()
    rows = ImportService.parse_csv(content)
    valid_items, errors = ImportService.validate_products_csv(rows)
    
    # Check SKU uniqueness against DB for valid items
    service = CatalogService(db)
    final_valid_items = []
    for item in valid_items:
        # We know item has 1 variant in this CSV structure
        sku = item.variants[0].sku
        if await service.is_sku_taken(shop_id, sku):
            errors.append({"row": 0, "reason": f"SKU '{sku}' already exists in DB (Row check skipped for detail)"})
        else:
            final_valid_items.append(item)

    # Convert valid_items (schemas) to dicts for storage
    data_to_store = [item.model_dump() for item in final_valid_items]
    token = ImportService.save_preview(shop_id, data_to_store, "product")

    return ImportPreviewResponse(
        import_token=token,
        valid_count=len(final_valid_items),
        invalid_count=len(errors),
        errors=errors,
        preview=data_to_store[:5]
    )


@router.post("/shops/{shop_id}/products/bulk-csv/confirm", status_code=status.HTTP_201_CREATED)
async def confirm_products_import(
    shop_id: uuid.UUID,
    request: ImportConfirmRequest,
    db: AsyncSession = Depends(get_db),
    shop=Depends(require_platform(ShopPlatform.MANUAL.value))
):
    """Commit the validated CSV data to the database."""
    preview = ImportService.get_preview(request.import_token)
    if not preview or preview["shop_id"] != shop_id or preview["type"] != "product":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired import token. Please re-upload your CSV."
        )

    service = CatalogService(db)
    imported_count = 0
    for item_dict in preview["data"]:
        schema = ProductCreate(**item_dict)
        await service.create_product(shop_id, schema)
        imported_count += 1
    
    ImportService.clear_preview(request.import_token)
    return {"message": f"Successfully imported {imported_count} products"}
