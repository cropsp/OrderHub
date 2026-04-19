"""
OrderHub CRM — Seed Script

Creates initial development data:
- 3 users (owner, manager, designer)
- 3 shops (2 Etsy + 1 Shopify)
- 15 orders across all statuses with realistic data
- OrderItems, OrderStatusHistory entries

Usage:
  python seed.py           # seed always
  python seed.py --if-empty # seed only if no users exist
"""

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func

from database import async_session_factory
from models import (
    User, UserRole,
    Shop, ShopPlatform,
    Customer,
    Order, OrderStatus, OrderItem, OrderStatusHistory,
)
from services.auth_service import hash_password


async def is_db_empty() -> bool:
    """Check if the database has any users."""
    async with async_session_factory() as session:
        result = await session.execute(select(func.count()).select_from(User))
        return result.scalar() == 0


async def seed():
    """Populate the database with development data."""
    async with async_session_factory() as session:
        # ─── Users ─────────────────────────────────────────────
        owner = User(
            id=uuid.uuid4(),
            email="owner@crm.local",
            hashed_password=hash_password("owner123"),
            full_name="Микола Шевченко",
            role=UserRole.OWNER,
        )
        manager = User(
            id=uuid.uuid4(),
            email="manager@crm.local",
            hashed_password=hash_password("manager123"),
            full_name="Оксана Коваленко",
            role=UserRole.MANAGER,
        )
        designer = User(
            id=uuid.uuid4(),
            email="designer@crm.local",
            hashed_password=hash_password("designer123"),
            full_name="Андрій Мельник",
            role=UserRole.DESIGNER,
        )
        session.add_all([owner, manager, designer])

        # ─── Shops ─────────────────────────────────────────────
        shop_lc = Shop(
            id=uuid.uuid4(),
            name="LeatherCraft UA",
            platform=ShopPlatform.ETSY,
            color="#F59E0B",
        )
        shop_lm = Shop(
            id=uuid.uuid4(),
            name="Leather by Mykola",
            platform=ShopPlatform.ETSY,
            color="#EF4444",
        )
        shop_sf = Shop(
            id=uuid.uuid4(),
            name="MyShopify Store",
            platform=ShopPlatform.SHOPIFY,
            color="#6366F1",
            shopify_store_url="https://my-leather-shop.myshopify.com",
        )
        session.add_all([shop_lc, shop_lm, shop_sf])

        # ─── Customers ────────────────────────────────────────
        customers_data = [
            ("Олексій Кравченко", "oleksii.k@gmail.com", "UA"),
            ("Sarah Mitchell", "sarah.m@outlook.com", "US"),
            ("John Davis", "john.d@gmail.com", "US"),
            ("Марія Бондаренко", "maria.b@ukr.net", "UA"),
            ("Hans Weber", "hans.w@web.de", "DE"),
            ("Ірина Ткаченко", "iryna.t@gmail.com", "UA"),
            ("Emily Brown", "emily.b@yahoo.com", "GB"),
            ("Петро Сидоренко", "petro.s@gmail.com", "UA"),
            ("Marie Dubois", "marie.d@orange.fr", "FR"),
            ("Дмитро Романенко", "dmytro.r@gmail.com", "UA"),
            ("Anna Schmidt", "anna.s@gmx.de", "DE"),
            ("Тетяна Кузьменко", "tetiana.k@gmail.com", "UA"),
        ]

        customers = []
        for name, email, country in customers_data:
            c = Customer(id=uuid.uuid4(), full_name=name, email=email, country=country)
            customers.append(c)
        session.add_all(customers)

        now = datetime.now(timezone.utc)

        # ─── Orders ────────────────────────────────────────────
        orders_spec = [
            # (shop, customer_idx, external_id, status, title, total, currency, days_ago, multi_item)
            (shop_lc, 0, "3001234501", OrderStatus.NEW, "Leather Wallet Brown", 45.00, "USD", 1, False),
            (shop_lc, 1, "3001234502", OrderStatus.NEW, "Belt Classic Black", 38.50, "USD", 2, False),
            (shop_lm, 2, "3001234503", OrderStatus.NEW, "Card Holder Minimalist", 25.00, "USD", 3, False),
            (shop_sf, 3, "SF-1001", OrderStatus.WAITING_INFO, "Гаманець з гравіюванням", 55.00, "EUR", 4, False),
            (shop_lc, 4, "3001234504", OrderStatus.WAITING_INFO, "Passport Cover + Wallet Set", 78.00, "EUR", 5, True),
            (shop_lm, 5, "3001234505", OrderStatus.INFO_RECEIVED, "Leather Journal A5", 42.00, "USD", 6, False),
            (shop_sf, 6, "SF-1002", OrderStatus.INFO_RECEIVED, "Custom Dog Collar", 32.00, "USD", 4, False),
            (shop_lc, 7, "3001234506", OrderStatus.DESIGN_PENDING, "Шкіряна сумка через плече", 120.00, "USD", 8, True),
            (shop_lm, 8, "3001234507", OrderStatus.DESIGN_PENDING, "Personalized Keychain Set", 35.00, "EUR", 5, True),
            (shop_lc, 9, "3001234508", OrderStatus.DESIGN_READY, "Leather Bracelet Engraved", 28.00, "USD", 10, False),
            (shop_sf, 10, "SF-1003", OrderStatus.IN_PRODUCTION, "Watch Strap Vintage", 65.00, "USD", 12, False),
            (shop_lm, 0, "3001234509", OrderStatus.IN_PRODUCTION, "Чохол для ноутбука 14\"", 85.00, "EUR", 9, False),
            (shop_lc, 11, "3001234510", OrderStatus.SHIPPED, "Leather Tote Bag", 145.00, "USD", 15, False),
            (shop_sf, 1, "SF-1004", OrderStatus.COMPLETED, "Belt Gift Set", 92.00, "USD", 25, False),
            (shop_lm, 3, "3001234511", OrderStatus.CANCELLED, "Phone Case Leather", 35.00, "EUR", 20, False),
        ]

        for shop, ci, ext_id, order_status, title, total, curr, days, multi in orders_spec:
            customer = customers[ci]
            ordered = now - timedelta(days=days)

            order = Order(
                id=uuid.uuid4(),
                external_id=ext_id,
                shop_id=shop.id,
                customer_id=customer.id,
                status=order_status,
                title=title if not multi else f"{title}",
                total_price=total,
                currency=curr,
                ordered_at=ordered,
                shipping_name=customer.full_name,
                shipping_country=customer.country,
                shipping_city="Kyiv" if customer.country == "UA" else "New York",
                shipping_street_1="вул. Хрещатик, 1" if customer.country == "UA" else "123 Main St",
                shipping_zip="01001" if customer.country == "UA" else "10001",
                customer_note="Please gift wrap" if ci % 3 == 0 else None,
            )

            # Assign designer for design statuses
            if order_status in (OrderStatus.DESIGN_PENDING, OrderStatus.DESIGN_READY):
                order.assigned_designer_id = designer.id
                order.assigned_at = ordered + timedelta(hours=2)

            # TTN for shipped
            if order_status == OrderStatus.SHIPPED:
                order.ttn_number = "20450000123456"
                order.ttn_created_at = now - timedelta(days=2)
                order.shipped_at = now - timedelta(days=2)

            # Financial data for completed
            if order_status == OrderStatus.COMPLETED:
                order.production_cost = round(total * 0.3, 2)
                order.shipping_np_cost = 8.50
                order.platform_fee = round(total * 0.065, 2)
                order.completed_at = now - timedelta(days=3)
                order.shipped_at = now - timedelta(days=8)

            session.add(order)

            # ─── OrderItems ────────────────────────────────────
            if multi:
                item1 = OrderItem(
                    order_id=order.id,
                    title=title.split("+")[0].strip() if "+" in title else title,
                    quantity=1,
                    unit_price=round(total * 0.6, 2),
                    currency=curr,
                    listing_id=f"LI-{ext_id}-1",
                    variations="Color: Brown",
                )
                item2 = OrderItem(
                    order_id=order.id,
                    title=title.split("+")[1].strip() if "+" in title else "Matching Accessory",
                    quantity=1,
                    unit_price=round(total * 0.4, 2),
                    currency=curr,
                    listing_id=f"LI-{ext_id}-2",
                    variations="Color: Brown, Size: M",
                )
                session.add_all([item1, item2])
            else:
                item = OrderItem(
                    order_id=order.id,
                    title=title,
                    quantity=1,
                    unit_price=total,
                    currency=curr,
                    listing_id=f"LI-{ext_id}-1",
                )
                session.add(item)

            # ─── Initial status history ────────────────────────
            history = OrderStatusHistory(
                order_id=order.id,
                changed_by_id=owner.id,
                from_status="none",
                to_status=order_status.value,
                comment="Initial import",
                changed_at=ordered,
            )
            session.add(history)

        await session.commit()
        print(f"✅ Seed complete: 3 users, 3 shops, {len(orders_spec)} orders")


async def main():
    if "--if-empty" in sys.argv:
        if not await is_db_empty():
            print("Database already has data, skipping seed.")
            return
    await seed()


if __name__ == "__main__":
    asyncio.run(main())
