import csv
import io
import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.order import Order, OrderItem, OrderStatus, OrderStatusHistory
from models.product import Product, ProductVariant
from models.shop import Shop
from schemas.common import ImportResult
from services.catalog_service import CatalogService
from services.customer_service import upsert_customer

logger = logging.getLogger(__name__)


def _compute_effective_sku(listing_id: str, raw_sku: Optional[str], used_in_listing: Set[str]) -> str:
    """Generate an SKU when CSV is blank: etsy-{listing_id} for the first variant,
    etsy-{listing_id}-{n} (n>=2) for subsequent ones, skipping any already used."""
    cleaned = (raw_sku or "").strip()
    if cleaned:
        return cleaned
    base = f"etsy-{listing_id}"
    if base not in used_in_listing:
        return base
    n = 2
    while f"{base}-{n}" in used_in_listing:
        n += 1
    return f"{base}-{n}"


def _parse_decimal(raw: Any) -> Optional[Decimal]:
    if raw in (None, "", " "):
        return None
    try:
        return Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None


async def _ensure_catalog_row(
    db: AsyncSession,
    shop: Shop,
    catalog_service: CatalogService,
    row: Dict[str, Any],
    catalog_cache: Dict[str, Dict[str, Any]],
    counters: Dict[str, int],
) -> Optional[ProductVariant]:
    """Lazily create Product + ProductVariant rows for a CSV row.
    Returns the variant the OrderItem should link to, or None when catalog work was skipped."""
    listing_id = (row.get("Listing ID") or "").strip()
    if not listing_id:
        return None

    cache = catalog_cache.get(listing_id)
    if cache is None:
        existing_product = await catalog_service.find_product_by_external_ref(shop.id, listing_id)
        cache = {
            "product": existing_product,
            "skus_in_listing": set(),
            "variants_by_sku": {},
        }
        if existing_product is not None:
            for v in existing_product.variants:
                if v.sku:
                    cache["skus_in_listing"].add(v.sku)
                    cache["variants_by_sku"][v.sku] = v
        catalog_cache[listing_id] = cache

    effective_sku = _compute_effective_sku(listing_id, row.get("SKU"), cache["skus_in_listing"])

    cached_variant = cache["variants_by_sku"].get(effective_sku)
    if cached_variant is not None:
        return cached_variant

    if await catalog_service.is_sku_taken(shop.id, effective_sku):
        return None

    product = cache["product"]
    if product is None:
        product = Product(
            id=uuid.uuid4(),
            shop_id=shop.id,
            title=(row.get("Item Name") or "Unknown Item")[:500],
            external_ref=listing_id,
        )
        db.add(product)
        cache["product"] = product
        counters["products_created"] += 1

    variations_text = (row.get("Variations") or "").strip() or None
    if variations_text and len(variations_text) > 255:
        variations_text = variations_text[:255]

    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=product.id,
        sku=effective_sku,
        variant_name=variations_text,
        weight_g=0,
        length_mm=0,
        width_mm=0,
        height_mm=0,
        price=_parse_decimal(row.get("Price")),
    )
    db.add(variant)

    cache["skus_in_listing"].add(effective_sku)
    cache["variants_by_sku"][effective_sku] = variant
    counters["variants_created"] += 1

    return variant


async def parse_etsy_csv(db: AsyncSession, shop: Shop, file_content: bytes, user_id: uuid.UUID) -> ImportResult:
    """Parses an Etsy CSV export and inserts/updates DB records."""
    
    # Strip UTF-8 BOM if present
    if file_content.startswith(b'\xef\xbb\xbf'):
        file_content = file_content[3:]
        
    text_content = file_content.decode('utf-8')
    csv_reader = csv.DictReader(io.StringIO(text_content))
    
    imported = 0
    skipped = 0
    errors = []
    total_processed_rows = 0
    catalog_cache: Dict[str, Dict[str, Any]] = {}
    catalog_counters: Dict[str, int] = {"products_created": 0, "variants_created": 0}
    catalog_service = CatalogService(db)

    # Group rows by Sale ID
    orders_data: Dict[str, list[Dict[str, Any]]] = {}
    rows_map: Dict[str, list[int]] = {}  # sale_id -> list of row numbers
    
    for row_num, row in enumerate(csv_reader, start=2): # +1 for header, +1 for 0-index
        total_processed_rows += 1
        sale_id = row.get("Sale ID") or row.get("Order ID")
        if not sale_id:
            errors.append({"row": row_num, "error": "Missing 'Sale ID' or 'Order ID' column/value"})
            continue
            
        if sale_id not in orders_data:
            orders_data[sale_id] = []
            rows_map[sale_id] = []
        orders_data[sale_id].append(row)
        rows_map[sale_id].append(row_num)
        
    # Failure threshold check (BE-3 audit requirement)
    if total_processed_rows > 0 and (len(errors) / total_processed_rows) > 0.2:
        return ImportResult(
            imported=0, 
            skipped=0, 
            errors=[{"error": f"Import aborted: {len(errors)}/{total_processed_rows} rows have format errors (>20% threshold)"}]
        )
        
    for sale_id, rows in orders_data.items():
        row_nums = rows_map.get(sale_id, [])
        try:
            # Check for duplicates based on external_id and shop_id
            existing = await db.execute(
                select(Order).where(Order.external_id == sale_id, Order.shop_id == shop.id)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue
                
            # First row contains the order-level information
            primary_row = rows[0]
            
            # Handle Date (Multiple formats fallback)
            date_str = primary_row.get("Sale Date", "")
            ordered_at = None
            date_formats = ["%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"]
            for fmt in date_formats:
                try:
                    ordered_at = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                    break
                except (ValueError, TypeError):
                    continue
            
            if not ordered_at:
                logger.warning(f"Invalid date format for Sale ID {sale_id}: {date_str}. Using current date.")
                ordered_at = datetime.now(timezone.utc)
                 
            # Customer
            email = primary_row.get("Buyer Email", "").strip() or f"order_{sale_id}@etsy.internal"
            customer_name = primary_row.get("Buyer", "Unknown Buyer").strip()
            country = primary_row.get("Ship Country", "US").strip()[:2] # Best effort
            
            customer = await upsert_customer(db, email, customer_name, country)
            
            # The total order price is typically listed on every row identically
            total_price = float(primary_row.get("Order Total") or primary_row.get("Item Total") or 0)
            
            # Create Order
            order = Order(
                id=uuid.uuid4(),
                external_id=sale_id,
                shop_id=shop.id,
                customer_id=customer.id,
                status=OrderStatus.NEW,
                title=f"Etsy Order {sale_id}",
                total_price=total_price, 
                currency=primary_row.get("Currency", "USD"),
                ordered_at=ordered_at,
                shipping_name=primary_row.get("Ship Name"),
                shipping_street_1=primary_row.get("Ship Address1"),
                shipping_street_2=primary_row.get("Ship Address2"),
                shipping_city=primary_row.get("Ship City"),
                shipping_state=primary_row.get("Ship State"),
                shipping_zip=primary_row.get("Ship Zipcode"),
                shipping_country=country,
            )
            db.add(order)
            
            # Status History
            history = OrderStatusHistory(
                id=uuid.uuid4(),
                order_id=order.id,
                changed_by_id=user_id,
                from_status="none",
                to_status=OrderStatus.NEW.value,
                comment="Imported from Etsy CSV"
            )
            db.add(history)
            
            # Order Items
            for row in rows:
                 # In etsy CSV sometimes it contains multiple quantities, some rows represent different items
                 variant: Optional[ProductVariant] = None
                 try:
                     variant = await _ensure_catalog_row(
                         db, shop, catalog_service, row, catalog_cache, catalog_counters
                     )
                 except Exception:
                     logger.exception(
                         "Catalog auto-create failed for sale_id=%s listing_id=%s; continuing with order import",
                         sale_id, row.get("Listing ID")
                     )

                 item = OrderItem(
                     order_id=order.id,
                     title=row.get("Item Name", "Unknown Item"),
                     quantity=int(row.get("Quantity", 1) or 1),
                     unit_price=float(row.get("Price", 0) or 0),
                     currency=row.get("Currency", "USD"),
                     sku=row.get("SKU"),
                     listing_id=row.get("Listing ID"),
                     variations=row.get("Variations"),
                     product_variant_id=variant.id if variant is not None else None,
                 )
                 db.add(item)

                 # Append to order title if not already
                 if order.title == f"Etsy Order {sale_id}":
                      order.title = item.title

            imported += 1

        except Exception as e:
            logger.exception(f"Error importing sale_id {sale_id}")
            errors.append({"sale_id": sale_id, "rows": row_nums, "error": str(e)})

    await db.flush() # Caller commits

    return ImportResult(
        imported=imported,
        skipped=skipped,
        errors=errors,
        products_created=catalog_counters["products_created"],
        variants_created=catalog_counters["variants_created"],
    )
