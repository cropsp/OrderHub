"""Shared catalog auto-create helper for importers (Etsy CSV, Shopify GraphQL sync).

Extracted from `services.etsy_parser._ensure_catalog_row` (IMP-1) when IMP-2
added Shopify as a second consumer. Platform-specific SKU resolution stays in
each importer; this module owns the shared lazy-insert / dedup / cache logic.

Invariants:
- Cache key (`external_product_id`) is unique within a single import call
  because each call is per-shop.
- The helper does NOT call `db.flush()` — callers control the flush boundary.
"""

import uuid
import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models.product import Product, ProductVariant
from models.shop import Shop
from services.catalog_service import CatalogService

logger = logging.getLogger(__name__)


_UNIT_TO_GRAMS = {
    "GRAMS": 1.0,
    "KILOGRAMS": 1000.0,
    "OUNCES": 28.3495,
    "POUNDS": 453.592,
}


def _weight_to_grams(weight: Optional[Dict[str, Any]]) -> int:
    """Convert a Shopify `inventoryItem.measurement.weight` subobject to grams.

    Returns 0 when the field is null/missing or the unit is unknown.
    """
    if not weight:
        return 0
    value = weight.get("value")
    if value is None:
        return 0
    factor = _UNIT_TO_GRAMS.get(weight.get("unit"))
    if factor is None:
        return 0
    try:
        return int(round(float(value) * factor))
    except (TypeError, ValueError):
        return 0


async def ensure_catalog_row(
    db: AsyncSession,
    shop: Shop,
    catalog_service: CatalogService,
    *,
    external_product_id: str,
    product_title: str,
    sku: str,
    variant_name: Optional[str] = None,
    external_variant_ref: Optional[str] = None,
    weight_g: int = 0,
    length_mm: int = 0,
    width_mm: int = 0,
    height_mm: int = 0,
    price: Optional[Decimal] = None,
    catalog_cache: Dict[str, Dict[str, Any]],
    counters: Dict[str, int],
) -> Optional[ProductVariant]:
    """Lazily create Product + ProductVariant rows for one external listing/variant.

    Returns the variant the OrderItem should FK-link to, or `None` when the
    SKU is already taken shop-wide (lazy insert: no orphan Product is added
    in that case).
    """
    if not external_product_id:
        return None

    cache = catalog_cache.get(external_product_id)
    if cache is None:
        existing_product = await catalog_service.find_product_by_external_ref(shop.id, external_product_id)
        cache = {
            "product": existing_product,
            "variants_by_sku": {},
        }
        if existing_product is not None:
            for v in existing_product.variants:
                if v.sku:
                    cache["variants_by_sku"][v.sku] = v
        catalog_cache[external_product_id] = cache

    cached_variant = cache["variants_by_sku"].get(sku)
    if cached_variant is not None:
        return cached_variant

    if await catalog_service.is_sku_taken(shop.id, sku):
        return None

    product = cache["product"]
    if product is None:
        product = Product(
            id=uuid.uuid4(),
            shop_id=shop.id,
            title=(product_title or "Unknown Item")[:500],
            external_ref=external_product_id,
        )
        db.add(product)
        cache["product"] = product
        counters["products_created"] += 1

    truncated_name = variant_name[:255] if variant_name else None

    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=product.id,
        sku=sku,
        variant_name=truncated_name,
        external_ref=external_variant_ref,
        weight_g=weight_g,
        length_mm=length_mm,
        width_mm=width_mm,
        height_mm=height_mm,
        price=price,
    )
    db.add(variant)

    cache["variants_by_sku"][sku] = variant
    counters["variants_created"] += 1

    return variant
