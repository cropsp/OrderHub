import csv
import io
import uuid
import logging
from datetime import datetime
from typing import Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.shop import Shop
from models.order import Order, OrderItem, OrderStatus, OrderStatusHistory
from schemas.common import ImportResult
from services.customer_service import upsert_customer

logger = logging.getLogger(__name__)


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
    
    # Group rows by Sale ID
    orders_data: Dict[str, list[Dict[str, Any]]] = {}
    
    for row_num, row in enumerate(csv_reader, start=2): # +1 for header, +1 for 0-index
        sale_id = row.get("Sale ID")
        if not sale_id:
            errors.append({"row": row_num, "error": "Missing 'Sale ID' column/value"})
            continue
            
        if sale_id not in orders_data:
            orders_data[sale_id] = []
        orders_data[sale_id].append(row)
        
    for sale_id, rows in orders_data.items():
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
            
            # Handle Date (Format: MM/DD/YY or similar in Etsy, depends on locale but usually standard)
            date_str = primary_row.get("Sale Date")
            try:
                # Assuming generic M/D/y format from Etsy. Need strict parsing in prod.
                ordered_at = datetime.strptime(date_str, "%m/%d/%y") 
            except (ValueError, TypeError):
                 # Fallback to now if parse fails, or log it
                 ordered_at = datetime.utcnow()
                 
            # Customer
            email = primary_row.get("Buyer Email", "").strip() or f"unknown_{sale_id}@example.com"
            customer_name = primary_row.get("Buyer", "Unknown Buyer").strip()
            country = primary_row.get("Ship Country", "US").strip()[:2] # Best effort
            
            customer = await upsert_customer(db, email, customer_name, country)
            
            total_price = sum(float(r.get("Order Total", 0) or 0) for r in rows if r == primary_row) # Only take Total once if repeated
            
            # Create Order
            order = Order(
                id=uuid.uuid4(),
                external_id=sale_id,
                shop_id=shop.id,
                customer_id=customer.id,
                status=OrderStatus.NEW,
                title=f"Etsy Order {sale_id}",
                total_price=float(primary_row.get("Order Total", 0) or 0), 
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
                 item = OrderItem(
                     order_id=order.id,
                     title=row.get("Item Name", "Unknown Item"),
                     quantity=int(row.get("Quantity", 1) or 1),
                     unit_price=float(row.get("Price", 0) or 0),
                     currency=row.get("Currency", "USD"),
                     sku=row.get("SKU"),
                     listing_id=row.get("Listing ID"),
                     variations=row.get("Variations")
                 )
                 db.add(item)
                 
                 # Append to order title if not already
                 if order.title == f"Etsy Order {sale_id}":
                      order.title = item.title

            imported += 1

        except Exception as e:
            logger.exception(f"Error importing sale_id {sale_id}")
            errors.append({"sale_id": sale_id, "error": str(e)})

    await db.flush() # Caller commits

    return ImportResult(imported=imported, skipped=skipped, errors=errors)
