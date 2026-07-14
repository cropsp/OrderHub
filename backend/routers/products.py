import uuid
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from logger import get_logger
from models.product import Product
from models.shop import Shop, ShopPlatform
from models.user import UserRole
from routers.dependencies import get_current_user, get_shop_for_user, require_platform, require_role
from schemas.bom import BomCostBreakdown, BomReadResponse, BomReplaceRequest
from schemas.product import ProductCreate, ProductRead, ProductUpdate, ProductVariantRead
from schemas.import_preview import ImportPreviewResponse, ImportConfirmRequest
from services import bom_service
from services.catalog_service import CatalogService
from services.encryption_service import decrypt_value
from services.file_storage import (
    FileTooLargeError,
    PRODUCT_IMAGE_MAX_BYTES,
    PRODUCT_IMAGE_MIME,
    delete_file,
    get_absolute_path,
    save_product_image,
    save_product_image_bytes,
    sniff_image_mime,
)
from services.import_service import ImportService
from services.shopify_sync import PRODUCT_IMAGE_QUERY, call_shopify_graphql

logger = get_logger("routers.products")

router = APIRouter(prefix="/api", tags=["Products"])

# Extension -> Content-Type for serving. Inverted from PRODUCT_IMAGE_MIME so the
# served type always derives from the extension WE generated, never from client input.
_EXT_TO_MIME = {ext: mime for mime, ext in PRODUCT_IMAGE_MIME.items()}


def _project_product(product: Product) -> ProductRead:
    """Serialize a Product, deriving image_url from image_path (PC-F-1)."""
    data = ProductRead.model_validate(product)
    data.image_url = f"/api/products/{product.id}/image" if product.image_path else None
    return data


@router.get("/shops/{shop_id}/products", response_model=List[ProductRead])
async def list_products(
    shop_id: uuid.UUID,
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db),
    shop=Depends(get_shop_for_user)
):
    """List all products for a shop (any platform). Access is gated by get_shop_for_user."""
    service = CatalogService(db)
    products = await service.get_products(shop_id, is_active=is_active)
    return [_project_product(p) for p in products]


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

    return _project_product(await service.create_product(shop_id, schema))


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
    return _project_product(product)


@router.patch("/products/{id}", response_model=ProductRead)
async def update_product(
    id: uuid.UUID,
    schema: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER))
):
    """Update product details."""
    service = CatalogService(db)
    try:
        product = await service.update_product(id, schema)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _project_product(product)


@router.delete("/products/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER))
):
    """Soft-delete a product."""
    service = CatalogService(db)
    await service.soft_delete_product(id)


# --- PC-F-1: Product image (single, product-level) ---


async def _load_product_or_404(db: AsyncSession, product_id: uuid.UUID) -> Product:
    service = CatalogService(db)
    product = await service.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


async def _set_product_image(db: AsyncSession, product: Product, relative_path: str) -> None:
    """Point the product at a new image, removing the file it replaced so a
    Replace never orphans bytes on the volume."""
    old_path = product.image_path
    product.image_path = relative_path
    await db.commit()
    await db.refresh(product)
    if old_path and old_path != relative_path:
        delete_file(old_path)


@router.post("/products/{id}/image", response_model=ProductRead)
async def upload_product_image(
    id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    """Upload or replace a product's image.

    The declared Content-Type is ignored — the type is sniffed from the leading
    bytes, because this file is served back to the browser.
    """
    product = await _load_product_or_404(db, id)

    head = await file.read(32)
    mime = sniff_image_mime(head)
    if mime is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported image type. Allowed: JPEG, PNG, WebP.",
        )
    await file.seek(0)

    try:
        relative_path, _size = await save_product_image(file, id, PRODUCT_IMAGE_MIME[mime])
    except FileTooLargeError:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds maximum size of {PRODUCT_IMAGE_MAX_BYTES // (1024 * 1024)} MB",
        )
    except Exception as e:
        logger.error(f"[PRODUCTS] Failed to save image for product {id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save product image")

    await _set_product_image(db, product, relative_path)
    return _project_product(product)


@router.delete("/products/{id}/image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_image(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    """Remove a product's image. Idempotent — 204 even if there is none."""
    product = await _load_product_or_404(db, id)

    old_path = product.image_path
    if old_path:
        product.image_path = None
        await db.commit()
        delete_file(old_path)


@router.get("/products/{id}/image")
async def get_product_image(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Serve a product's image bytes.

    Authenticated: the frontend fetches this as a blob (the JWT is an in-memory
    header, so a bare <img src> would 401). Content-Type derives from the
    extension we generated at upload, never from stored client input.
    """
    product = await _load_product_or_404(db, id)
    if not product.image_path:
        raise HTTPException(status_code=404, detail="Product has no image")

    abs_path = get_absolute_path(product.image_path)
    if not abs_path:
        raise HTTPException(status_code=404, detail="Image content not found on disk")

    media_type = _EXT_TO_MIME.get(abs_path.suffix.lstrip("."), "application/octet-stream")
    return FileResponse(
        path=abs_path,
        media_type=media_type,
        content_disposition_type="inline",
    )


@router.post("/products/{id}/image/from-shopify", response_model=ProductRead)
async def pull_product_image_from_shopify(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    """Fetch the Shopify listing's featured image and store it as the product image.

    On-demand only — order sync never pulls images.
    """
    product = await _load_product_or_404(db, id)

    shop = await db.get(Shop, product.shop_id)
    if not shop or shop.platform != ShopPlatform.SHOPIFY:
        raise HTTPException(status_code=409, detail="Product is not from a Shopify shop")
    if not product.external_ref:
        raise HTTPException(status_code=409, detail="Product has no Shopify reference")
    if not shop.shopify_store_url or not shop.shopify_access_token_encrypted:
        raise HTTPException(status_code=409, detail="Shop is missing Shopify credentials")

    token = decrypt_value(shop.shopify_access_token_encrypted)
    # external_ref stores the numeric id (_parse_shopify_gid strips the GID at
    # import time), so it must be re-wrapped to query Shopify by id.
    gid = f"gid://shopify/Product/{product.external_ref}"

    try:
        data = await call_shopify_graphql(
            str(shop.shopify_store_url), token, PRODUCT_IMAGE_QUERY, {"id": gid}
        )
    except Exception as e:
        logger.error(f"[PRODUCTS] Shopify image fetch failed for product {id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to reach Shopify")

    image_url = ((data.get("product") or {}).get("featuredImage") or {}).get("url")
    if not image_url:
        raise HTTPException(status_code=404, detail="Shopify listing has no featured image")

    # The remote URL is untrusted input — same cap and same sniff as a manual upload.
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("GET", image_url) as response:
                response.raise_for_status()
                content = b""
                async for chunk in response.aiter_bytes(1024 * 1024):
                    content += chunk
                    if len(content) > PRODUCT_IMAGE_MAX_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=(
                                "Shopify image exceeds maximum size of "
                                f"{PRODUCT_IMAGE_MAX_BYTES // (1024 * 1024)} MB"
                            ),
                        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PRODUCTS] Shopify image download failed for product {id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to download image from Shopify")

    mime = sniff_image_mime(content[:32])
    if mime is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Shopify image is not a supported type (JPEG, PNG, WebP).",
        )

    relative_path, _size = await save_product_image_bytes(content, id, PRODUCT_IMAGE_MIME[mime])
    await _set_product_image(db, product, relative_path)
    return _project_product(product)


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


# --- MAT-3: Bill of Materials ---


@router.get("/products/{id}/bom", response_model=BomReadResponse)
async def get_product_bom(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    """Fetch a product's recipe + per-currency cost preview."""
    items, has_inactive = await bom_service.get_bom(db, product_id=id)
    cost = await bom_service.compute_bom_cost(db, product_id=id)
    return BomReadResponse(
        items=[bom_service.project_bom_item(item) for item in items],
        cost=cost,
        has_inactive_material=has_inactive,
    )


@router.put("/products/{id}/bom", response_model=BomReadResponse)
async def replace_product_bom(
    id: uuid.UUID,
    payload: BomReplaceRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    """Replace a product's full recipe. DELETE-all + bulk INSERT in one
    transaction. Empty list clears the recipe."""
    items, has_inactive = await bom_service.replace_bom(
        db, product_id=id, items=payload.items
    )
    await db.commit()
    cost = await bom_service.compute_bom_cost(db, product_id=id)
    return BomReadResponse(
        items=[bom_service.project_bom_item(item) for item in items],
        cost=cost,
        has_inactive_material=has_inactive,
    )


@router.get(
    "/products/{id}/bom/cost",
    response_model=List[BomCostBreakdown],
)
async def get_product_bom_cost(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    """Recompute recipe cost without fetching the full BOM. Cheap endpoint
    for a manual "Refresh cost" affordance in the editor."""
    return await bom_service.compute_bom_cost(db, product_id=id)
