import uuid
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from logger import get_logger
from models.product import Product
from models.shop import Shop, ShopPlatform
from models.user import Capability, UserRole
from routers.dependencies import (
    assert_capability,
    assert_shop_access,
    get_current_user,
    get_shop_for_user,
    require_platform,
    require_role,
)
from services.access_service import get_capabilities
from schemas.bom import (
    BomCostEnvelope,
    BomItemRead,
    BomReadResponse,
    BomReplaceRequest,
)
from schemas.product import ProductCreate, ProductRead, ProductUpdate, ProductVariantRead
from schemas.import_preview import ImportPreviewResponse, ImportConfirmRequest
from services import bom_service, fx_service
from services.catalog_service import CatalogService
from services.file_storage import (
    FileTooLargeError,
    PRODUCT_IMAGE_MAX_BYTES,
    PRODUCT_IMAGE_MIME,
    delete_file,
    get_absolute_path,
    save_product_image,
    sniff_image_mime,
)
from services.import_service import ImportService
from services.product_image_service import fetch_and_store_shopify_image

logger = get_logger("routers.products")

router = APIRouter(prefix="/api", tags=["Products"])

# Extension -> Content-Type for serving. Inverted from PRODUCT_IMAGE_MIME so the
# served type always derives from the extension WE generated, never from client input.
_EXT_TO_MIME = {ext: mime for mime, ext in PRODUCT_IMAGE_MIME.items()}


def _project_product(product: Product, *, can_view_costs: bool = True) -> ProductRead:
    """Serialize a Product, deriving image_url from image_path (PC-F-1).

    USER-ACCESS-2: `cost_price` is a per-variant cost input — nulled on every
    variant unless the caller holds VIEW_COSTS. `price` (the selling price) is
    revenue-side and stays visible.
    """
    data = ProductRead.model_validate(product)
    data.image_url = f"/api/products/{product.id}/image" if product.image_path else None
    if not can_view_costs:
        # cost_price lives on ProductVariantRead, not on ProductRead — assigning
        # it at the product level raised ValueError (Pydantic rejects unknown
        # fields), 500-ing every product read for a caller without VIEW_COSTS
        # while never censoring anything.
        for variant in data.variants:
            variant.cost_price = None
    return data


async def _can_view_costs(db: AsyncSession, user) -> bool:
    """Resolve the caller's VIEW_COSTS capability (USER-ACCESS-2)."""
    caps = await get_capabilities(db, user)
    return caps.has(Capability.VIEW_COSTS)


@router.get("/shops/{shop_id}/products", response_model=List[ProductRead])
async def list_products(
    shop_id: uuid.UUID,
    is_active: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db),
    shop=Depends(get_shop_for_user),
    user=Depends(get_current_user),
):
    """List all products for a shop (any platform). Access is gated by get_shop_for_user."""
    service = CatalogService(db)
    products = await service.get_products(shop_id, is_active=is_active)
    cvc = await _can_view_costs(db, user)
    return [_project_product(p, can_view_costs=cvc) for p in products]


@router.post("/shops/{shop_id}/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    shop_id: uuid.UUID,
    schema: ProductCreate,
    db: AsyncSession = Depends(get_db),
    shop=Depends(require_platform(ShopPlatform.MANUAL.value)),
    user=Depends(get_current_user),
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

    cvc = await _can_view_costs(db, user)
    try:
        product = await service.create_product(shop_id, schema)
    except ValueError as e:
        # WH-5: an unusable default_packaging_box_id. Mirrors the PATCH route
        # below so both surfaces answer the same way.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return _project_product(product, can_view_costs=cvc)


@router.get("/products/{id}", response_model=ProductRead)
async def get_product(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user)
):
    """Get product details."""
    product = await _load_product_checked(db, id, user)
    return _project_product(product, can_view_costs=await _can_view_costs(db, user))


@router.patch("/products/{id}", response_model=ProductRead)
async def update_product(
    id: uuid.UUID,
    schema: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER))
):
    """Update product details."""
    await _load_product_checked(db, id, user)
    service = CatalogService(db)
    try:
        product = await service.update_product(id, schema)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _project_product(product, can_view_costs=await _can_view_costs(db, user))


@router.delete("/products/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER))
):
    """Soft-delete a product."""
    await _load_product_checked(db, id, user)
    service = CatalogService(db)
    await service.soft_delete_product(id)


# --- PC-F-1: Product image (single, product-level) ---


async def _load_product_or_404(db: AsyncSession, product_id: uuid.UUID) -> Product:
    service = CatalogService(db)
    product = await service.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


async def _load_product_checked(db: AsyncSession, product_id: uuid.UUID, user) -> Product:
    """Load a product and verify the caller can access its shop (USER-ACCESS-1).

    Product-by-id endpoints resolve the shop only indirectly via product.shop_id;
    without this a scoped manager/designer could read or edit catalog in a shop
    they were not granted.
    """
    product = await _load_product_or_404(db, product_id)
    await assert_shop_access(db, product.shop_id, user)
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
    product = await _load_product_checked(db, id, user)

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
    return _project_product(product, can_view_costs=await _can_view_costs(db, user))


@router.delete("/products/{id}/image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_image(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    """Remove a product's image. Idempotent — 204 even if there is none."""
    product = await _load_product_checked(db, id, user)

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
    product = await _load_product_checked(db, id, user)
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

    On-demand only — order sync never pulls images. The fetch/download/store logic
    lives in product_image_service (shared with the bulk backfill, ORDER-CARD-1).
    """
    product = await _load_product_checked(db, id, user)
    shop = await db.get(Shop, product.shop_id)
    await fetch_and_store_shopify_image(db, shop, product)
    return _project_product(product, can_view_costs=await _can_view_costs(db, user))


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


def _strip_bom_costs(items: list[BomItemRead]) -> list[BomItemRead]:
    """Zero the per-line cost fields for a caller without VIEW_COSTS
    (USER-ACCESS-2). Recipe structure (materials, quantities, names) stays;
    only the cost numbers are hidden."""
    return [
        item.model_copy(
            update={
                "material_current_unit_cost": Decimal("0"),
                "line_cost": Decimal("0"),
            }
        )
        for item in items
    ]


async def _bom_response(
    db: AsyncSession,
    product_id: uuid.UUID,
    items: list,
    has_inactive: bool,
    user,
    *,
    target_currency: str | None = None,
) -> BomReadResponse:
    """Build a BomReadResponse, nulling all cost numbers (per-line + the cost
    preview + the FX conversion) unless the caller holds VIEW_COSTS. Shared by
    the BOM read AND replace endpoints so their cost censoring cannot drift
    (USER-ACCESS-2)."""
    projected = [bom_service.project_bom_item(item) for item in items]
    if await _can_view_costs(db, user):
        fx = await fx_service.resolve(db)
        envelope = await bom_service.compute_bom_cost(
            db, product_id=product_id, target_currency=target_currency, fx=fx
        )
        cost, cost_converted = envelope.basis, envelope.converted
    else:
        projected = _strip_bom_costs(projected)
        # The converted total is a cost like any other — it must be nulled here
        # too. _strip_bom_costs only covers the per-line fields, which is why no
        # converted figure is ever put on BomItemRead: a new cost field there
        # would slip past that hardcoded list.
        cost, cost_converted = [], None
    return BomReadResponse(
        items=projected,
        cost=cost,
        cost_converted=cost_converted,
        has_inactive_material=has_inactive,
    )


@router.get("/products/{id}/bom", response_model=BomReadResponse)
async def get_product_bom(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    """Fetch a product's recipe + per-currency cost preview.

    USER-ACCESS-2: the recipe structure is visible to any OWNER/MANAGER with shop
    access, but the cost preview and per-line costs are nulled unless the caller
    holds VIEW_COSTS.
    """
    await _load_product_checked(db, id, user)
    items, has_inactive = await bom_service.get_bom(db, product_id=id)
    return await _bom_response(db, id, items, has_inactive, user)


@router.put("/products/{id}/bom", response_model=BomReadResponse)
async def replace_product_bom(
    id: uuid.UUID,
    payload: BomReplaceRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    """Replace a product's full recipe. DELETE-all + bulk INSERT in one
    transaction. Empty list clears the recipe.

    USER-ACCESS-2: the echoed cost preview is nulled for a caller without
    VIEW_COSTS, same as the read endpoint."""
    await _load_product_checked(db, id, user)
    items, has_inactive = await bom_service.replace_bom(
        db, product_id=id, items=payload.items
    )
    await db.commit()
    return await _bom_response(db, id, items, has_inactive, user)


@router.get(
    "/products/{id}/bom/cost",
    response_model=BomCostEnvelope,
)
async def get_product_bom_cost(
    id: uuid.UUID,
    in_currency: str | None = Query(
        None,
        alias="in",
        max_length=3,
        description=(
            "Convert the whole recipe into this currency (e.g. 'USD'). Omit to "
            "get only the per-currency basis. Only UAH<->USD is supported; any "
            "other pair, or a missing rate, returns converted=null."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
):
    """Recompute recipe cost without fetching the full BOM. Cheap endpoint
    for a manual "Refresh cost" affordance in the editor.

    FX-CONVERSION: `?in=USD` converts the UAH basis at the current rate, so the
    preview can show what a USD shop's order will actually book. The target is
    explicit rather than derived from the product's shop — see
    bom_service.compute_bom_cost for why.

    USER-ACCESS-2: this endpoint returns ONLY cost, so it is 403 (not nulled)
    for a caller without VIEW_COSTS."""
    await _load_product_checked(db, id, user)
    await assert_capability(db, Capability.VIEW_COSTS, user)
    fx = await fx_service.resolve(db)
    return await bom_service.compute_bom_cost(
        db, product_id=id, target_currency=in_currency, fx=fx
    )
