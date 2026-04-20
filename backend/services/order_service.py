"""
OrderHub CRM — Order Service
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, or_, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from models.order import Order, OrderItem, OrderStatus, OrderStatusHistory, ALLOWED_TRANSITIONS
from models.user import User, UserRole
from schemas.order import OrderCreate, OrderUpdate, OrderFilters
from services.customer_service import upsert_customer


# ─── Read ──────────────────────────────────────────────────

async def get_orders_filtered(
    db: AsyncSession,
    skip: int,
    limit: int,
    filters: OrderFilters
) -> tuple[list[Order], int]:
    """Get orders with total count, applying all filters."""
    
    # Base query for orders
    query = select(Order).options(
        selectinload(Order.customer),
        selectinload(Order.shop)
    )
    
    # Base query for count
    count_query = select(func.count()).select_from(Order)
    
    # Apply filters to both
    conditions = []
    
    if filters.status:
        conditions.append(Order.status == filters.status)
        
    if filters.shop_id:
        conditions.append(Order.shop_id == filters.shop_id)
        
    if filters.assigned_designer_id:
        conditions.append(Order.assigned_designer_id == filters.assigned_designer_id)
        
    if filters.search:
        # Search by external_id or title
        term = f"%{filters.search}%"
        conditions.append(or_(
            Order.external_id.ilike(term),
            Order.title.ilike(term)
        ))
        
    if conditions:
        query = query.where(*conditions)
        count_query = count_query.where(*conditions)
        
    # Execution
    total = await db.scalar(count_query) or 0
    
    query = query.order_by(Order.ordered_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    orders = list(result.scalars().all())
    
    return orders, total


async def get_order_detail(db: AsyncSession, order_id: uuid.UUID) -> Order | None:
    """Get full order detail including items and history."""
    query = select(Order).where(Order.id == order_id).options(
        selectinload(Order.customer),
        selectinload(Order.shop),
        selectinload(Order.items),
        selectinload(Order.status_history).selectinload(OrderStatusHistory.changed_by),
        selectinload(Order.attachments)
    )
    result = await db.execute(query)
    order = result.scalar_one_or_none()
    
    if order:
        # Compute changed_by_name for history
        for history in order.status_history:
            history.changed_by_name = history.changed_by.full_name if history.changed_by else "Unknown"
            
    return order


# ─── Write ─────────────────────────────────────────────────

async def change_order_status(
    db: AsyncSession,
    order: Order,
    new_status: OrderStatus,
    user: User,
    comment: str | None = None
) -> Order:
    """Change order status with validation and history logging."""
    
    if new_status == order.status:
        return order
        
    # Check allowed transitions (Only enforce for Designers; Owner/Manager can override for manual correction)
    allowed_targets = ALLOWED_TRANSITIONS.get(order.status, set())
    if new_status not in allowed_targets and user.role not in (UserRole.OWNER, UserRole.MANAGER):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from {order.status.value} to {new_status.value}"
        )
        
    # Check roles
    if order.status == OrderStatus.CANCELLED and user.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can reopen cancelled orders"
        )
        
    # Auto-set timestamps
    now = datetime.now(timezone.utc)
    if new_status == OrderStatus.SHIPPED:
        if order.shipped_at is None:
            order.shipped_at = now
    elif new_status == OrderStatus.COMPLETED:
        if order.completed_at is None:
            order.completed_at = now
            
    # Auto-assign designer if moving to design phases
    if new_status in (OrderStatus.DESIGN_PENDING, OrderStatus.DESIGN_READY):
        if order.assigned_designer_id is None and user.role == UserRole.DESIGNER:
            order.assigned_designer_id = user.id
            order.assigned_at = now

    old_status = order.status
    order.status = new_status
    
    # Create history entry
    history = OrderStatusHistory(
        id=uuid.uuid4(),
        order_id=order.id,
        changed_by_id=user.id,
        from_status=old_status.value,
        to_status=new_status.value,
        comment=comment
    )
    db.add(history)
    
    await db.flush()
    return order


async def create_order(db: AsyncSession, data: OrderCreate, user: User) -> Order:
    """Manual order creation."""
    # Customupsert -> Create order -> Default History
    customer = await upsert_customer(db, data.email, data.full_name, data.shipping_country)
    
    order = Order(
        id=uuid.uuid4(),
        external_id=data.external_id,
        shop_id=data.shop_id,
        customer_id=customer.id,
        status=OrderStatus.NEW,
        title=data.title,
        total_price=data.total_price,
        currency=data.currency,
        ordered_at=data.ordered_at,
        shipping_name=data.shipping_name,
        shipping_phone=data.shipping_phone,
        shipping_street_1=data.shipping_street_1,
        shipping_street_2=data.shipping_street_2,
        shipping_city=data.shipping_city,
        shipping_state=data.shipping_state,
        shipping_zip=data.shipping_zip,
        shipping_country=data.shipping_country
    )
    db.add(order)
    await db.flush()
    
    # Initial history
    history = OrderStatusHistory(
        id=uuid.uuid4(),
        order_id=order.id,
        changed_by_id=user.id,
        from_status="none",
        to_status=OrderStatus.NEW.value,
        comment="Order manually created"
    )
    db.add(history)
    
    # Empty items for manual order (can be updated later)
    # This just ensures we have a valid Order detail response
    
    await db.flush()
    # Eager load relationships for response
    return await get_order_detail(db, order.id)


async def update_order(db: AsyncSession, order: Order, data: OrderUpdate, user: User) -> Order:
    """Partial update with role restrictions."""
    
    update_data = data.model_dump(exclude_unset=True)
    
    # Security: role check for financial fields
    financial_fields = {"production_cost", "shipping_np_cost", "platform_fee"}
    if any(k in update_data for k in financial_fields) and user.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can modify financial fields"
        )
        
    for key, value in update_data.items():
        setattr(order, key, value)
        
    await db.flush()
    return order
