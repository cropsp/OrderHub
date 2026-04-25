import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.shop import ShopPlatform
from models.user import UserRole
from routers.dependencies import get_current_user, get_shop_for_user, require_platform, require_role
from schemas.packaging import PackagingBoxCreate, PackagingBoxRead, PackagingBoxUpdate
from schemas.import_preview import ImportPreviewResponse, ImportConfirmRequest
from services.catalog_service import CatalogService
from services.import_service import ImportService


router = APIRouter(prefix="/api", tags=["Packaging"])


@router.get("/shops/{shop_id}/packaging-boxes", response_model=List[PackagingBoxRead])
async def list_packaging(
    shop_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    shop=Depends(require_platform(ShopPlatform.MANUAL.value))
):
    """List all packaging boxes for a manual shop."""
    service = CatalogService(db)
    return await service.get_packaging_boxes(shop_id)


@router.post("/shops/{shop_id}/packaging-boxes", response_model=PackagingBoxRead, status_code=status.HTTP_201_CREATED)
async def create_packaging(
    shop_id: uuid.UUID,
    schema: PackagingBoxCreate,
    db: AsyncSession = Depends(get_db),
    shop=Depends(require_platform(ShopPlatform.MANUAL.value))
):
    """Create a new packaging box."""
    service = CatalogService(db)
    return await service.create_packaging_box(shop_id, schema)


@router.patch("/packaging-boxes/{id}", response_model=PackagingBoxRead)
async def update_packaging(
    id: uuid.UUID,
    schema: PackagingBoxUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER))
):
    """Update packaging box details."""
    service = CatalogService(db)
    box = await service.update_packaging_box(id, schema)
    if not box:
        raise HTTPException(status_code=404, detail="Packaging box not found")
    return box


@router.delete("/packaging-boxes/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_packaging(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER))
):
    """Hard-delete a packaging box."""
    service = CatalogService(db)
    await service.delete_packaging_box(id)


# --- Bulk CSV Import (Two-step) ---

@router.post("/shops/{shop_id}/packaging-boxes/bulk-csv/preview", response_model=ImportPreviewResponse)
async def preview_packaging_import(
    shop_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    shop=Depends(require_platform(ShopPlatform.MANUAL.value))
):
    """Validate CSV and return a preview of packaging boxes to be imported."""
    content = await file.read()
    rows = ImportService.parse_csv(content)
    valid_items, errors = ImportService.validate_packaging_csv(rows)

    # Convert valid_items (schemas) to dicts for storage
    data_to_store = [item.model_dump() for item in valid_items]
    token = ImportService.save_preview(shop_id, data_to_store, "packaging")

    return ImportPreviewResponse(
        import_token=token,
        valid_count=len(valid_items),
        invalid_count=len(errors),
        errors=errors,
        preview=data_to_store[:5]
    )


@router.post("/shops/{shop_id}/packaging-boxes/bulk-csv/confirm", status_code=status.HTTP_201_CREATED)
async def confirm_packaging_import(
    shop_id: uuid.UUID,
    request: ImportConfirmRequest,
    db: AsyncSession = Depends(get_db),
    shop=Depends(require_platform(ShopPlatform.MANUAL.value))
):
    """Commit the validated CSV data to the database."""
    preview = ImportService.get_preview(request.import_token)
    if not preview or preview["shop_id"] != shop_id or preview["type"] != "packaging":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired import token. Please re-upload your CSV."
        )

    service = CatalogService(db)
    imported_count = 0
    for item_dict in preview["data"]:
        schema = PackagingBoxCreate(**item_dict)
        await service.create_packaging_box(shop_id, schema)
        imported_count += 1
    
    ImportService.clear_preview(request.import_token)
    return {"message": f"Successfully imported {imported_count} packaging boxes"}
