"""Shared Shopify featured-image pull (PC-F-1).

Single source of truth for "fetch a product's Shopify featured image and store it
as the product image", used by BOTH the on-demand single-product endpoint
(`POST /products/{id}/image/from-shopify`) and the shop-wide bulk backfill
(`POST /shops/{shop_id}/backfill-product-images`, ORDER-CARD-1 Part 2).

Order sync never pulls images — this stays deliberately separate from the sync
(the same PC-F-1 separation the single endpoint documents).
"""

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from logger import get_logger
from models.product import Product
from models.shop import Shop, ShopPlatform
from services.encryption_service import decrypt_value
from services.file_storage import (
    PRODUCT_IMAGE_MAX_BYTES,
    PRODUCT_IMAGE_MIME,
    delete_file,
    save_product_image_bytes,
    sniff_image_mime,
)
from services.shopify_sync import PRODUCT_IMAGE_QUERY, call_shopify_graphql

logger = get_logger("services.product_image")


async def _store_product_image(db: AsyncSession, product: Product, relative_path: str) -> None:
    """Point the product at a new image and commit, removing the file it replaced
    so a replace never orphans bytes on the volume. (expire_on_commit=False keeps
    other loaded rows — e.g. the shared shop — usable across a bulk loop.)"""
    old_path = product.image_path
    product.image_path = relative_path
    await db.commit()
    await db.refresh(product)
    if old_path and old_path != relative_path:
        delete_file(old_path)


async def fetch_and_store_shopify_image(db: AsyncSession, shop: Shop, product: Product) -> None:
    """Pull `product`'s Shopify featured image and store it as the product image.

    Raises HTTPException on every failure mode (non-Shopify shop / missing ref /
    missing creds → 409; no featured image → 404; unreachable/broken download →
    502; oversize → 413; unsupported type → 415). The single endpoint surfaces the
    exception directly; the bulk pass catches it and counts (404 = "no image",
    everything else = an error entry).
    """
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
        logger.error(f"[PRODUCT_IMAGE] Shopify image fetch failed for product {product.id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to reach Shopify")

    image_url = ((data.get("product") or {}).get("featuredImage") or {}).get("url")
    if not image_url:
        raise HTTPException(status_code=404, detail="Shopify listing has no featured image")

    # The remote URL is untrusted input — cap the download and sniff the bytes,
    # same as a manual upload.
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
        logger.error(f"[PRODUCT_IMAGE] Shopify image download failed for product {product.id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to download image from Shopify")

    mime = sniff_image_mime(content[:32])
    if mime is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Shopify image is not a supported type (JPEG, PNG, WebP).",
        )

    relative_path, _size = await save_product_image_bytes(content, product.id, PRODUCT_IMAGE_MIME[mime])
    await _store_product_image(db, product, relative_path)
