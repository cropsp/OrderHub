"""
OrderHub CRM — Customer Service
"""

import uuid
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.customer import Customer
from models.order import Order


async def upsert_customer(
    db: AsyncSession, 
    email: str, 
    full_name: str, 
    country: str | None = None,
    phone: str | None = None,
    shipping_city: str | None = None,
    shipping_city_ref: str | None = None,
    shipping_warehouse_ref: str | None = None
) -> Customer:
    """Finds a customer by email, updates name/country/shipping, or creates a new one."""
    email = email.lower().strip()
    
    result = await db.execute(select(Customer).where(Customer.email == email))
    customer = result.scalar_one_or_none()

    if customer:
        # Update existing
        customer.full_name = full_name
        if country: customer.country = country
        if phone: customer.phone = phone
        if shipping_city: customer.shipping_city = shipping_city
        if shipping_city_ref: customer.shipping_city_ref = shipping_city_ref
        if shipping_warehouse_ref: customer.shipping_warehouse_ref = shipping_warehouse_ref
    else:
        # Create new
        customer = Customer(
            id=uuid.uuid4(),
            email=email,
            full_name=full_name,
            country=country,
            phone=phone,
            shipping_city=shipping_city,
            shipping_city_ref=shipping_city_ref,
            shipping_warehouse_ref=shipping_warehouse_ref
        )
        db.add(customer)
        
    await db.flush()
    return customer


async def get_customer_with_order_count(
    db: AsyncSession, customer_id: uuid.UUID
) -> Customer | None:
    """Fetches a customer and computes their total order count."""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    
    if not customer:
        return None
        
    count_result = await db.execute(
        select(func.count()).select_from(Order).where(Order.customer_id == customer_id)
    )
    customer.order_count = count_result.scalar() or 0
    return customer
