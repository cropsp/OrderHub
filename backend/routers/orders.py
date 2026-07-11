"""
OrderHub CRM — Orders Router
"""

import uuid
import csv
import io
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.order import OrderStatus
from models.user import User, UserRole
from schemas.order import (
    OrderFilters, OrderListResponse, OrderResponse, 
    OrderCreate, OrderUpdate, StatusChangeRequest,
    OrderItemCreate, OrderItemUpdate, OrderItemResponse
)
from schemas.common import PaginatedResponse
from schemas.parcel import ParcelEstimate
from routers.dependencies import get_current_user, require_role
from services.order_service import (
    get_orders_filtered, get_order_detail,
    create_order, update_order, change_order_status,
    add_order_item, update_order_item, delete_order_item,
    redact_financial_comment
)
from services.parcel_calculator import calculate_parcel_estimate
from logger import get_logger

logger = get_logger("routers.orders")


router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("", response_model=PaginatedResponse[OrderListResponse])
async def list_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    # Filters
    status: OrderStatus | None = Query(None),
    shop_id: uuid.UUID | None = Query(None),
    search: str | None = Query(None),
    # Dependency
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List orders with pagination and filtering."""
    filters = OrderFilters(
        status=status,
        shop_id=shop_id,
        search=search,
    )
    
    # Designer sees only their own assigned orders
    if current_user.role == UserRole.DESIGNER:
        filters.assigned_designer_id = current_user.id
        
    skip = (page - 1) * limit
    orders, total = await get_orders_filtered(db, skip, limit, filters)
    pages = (total + limit - 1) // limit
    
    # Map to schema manually to include relationships without lazy-loading issues
    items = []
    for o in orders:
        data = OrderListResponse.model_validate(o).model_dump()
        data["shop_name"] = o.shop.name if o.shop else None
        data["platform"] = o.shop.platform.value if o.shop else None
        data["customer_name"] = o.customer.full_name if o.customer else None
        items.append(OrderListResponse(**data))
        
    return PaginatedResponse[OrderListResponse](
        items=items,
        total=total,
        page=page,
        limit=limit,
        pages=pages
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full order detail."""
    order = await get_order_detail(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # Check access for designer
    if current_user.role == UserRole.DESIGNER and order.assigned_designer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not assigned to this order")
        
    data = OrderResponse.model_validate(order).model_dump()
    data["shop_name"] = order.shop.name if order.shop else None
    data["platform"] = order.shop.platform.value if order.shop else None
    data["customer_name"] = order.customer.full_name if order.customer else None
    
    # Owner-only financial data: censor the body fields AND redact the values that
    # leak into audit-history comments for every non-owner role (managers + assigned
    # designers). Only OWNER writes these fields, so only OWNER sees the raw values.
    if current_user.role != UserRole.OWNER:
        data["production_cost"] = None
        data["shipping_np_cost"] = None
        data["platform_fee"] = None
        for entry in data.get("status_history", []):
            entry["comment"] = redact_financial_comment(entry.get("comment"))

    return OrderResponse(**data)


@router.get("/{order_id}/parcel-estimate", response_model=ParcelEstimate)
async def get_order_parcel_estimate(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Calculate and return parcel dimensions/weight based on items."""
    # 1. Fetch order
    order = await get_order_detail(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # 2. Check access
    if current_user.role == UserRole.DESIGNER and order.assigned_designer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not assigned to this order")
        
    # 3. Calculate estimate
    try:
        estimate = await calculate_parcel_estimate(db, str(order_id))
    except ValueError as e:
        logger.warning(f"[ORDERS] Parcel estimate validation error for {order_id}: {e}")
        raise HTTPException(status_code=400, detail="Unable to calculate parcel estimate for this order")
        
    # 4. Cache results if parcel_override is False
    if not order.parcel_override:
        order.computed_parcel_weight_g = estimate.total_weight_g
        order.computed_parcel_length_mm = estimate.parcel_length_mm
        order.computed_parcel_width_mm = estimate.parcel_width_mm
        order.computed_parcel_height_mm = estimate.parcel_height_mm
        order.computed_packaging_box_id = estimate.selected_packaging.id if estimate.selected_packaging else None
        
        await db.commit()
        
    return estimate


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_new_order(
    body: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually create a new order."""
    if current_user.role == UserRole.DESIGNER:
        raise HTTPException(status_code=403, detail="Designers cannot create orders manually")
        
    logger.info(f"Creating new order for user {current_user.email}")
    order = await create_order(db, body, current_user)
    await db.commit()
    logger.info(f"Order {order.id} created and committed")
    return await get_order(order.id, current_user, db)


@router.patch("/{order_id}", response_model=OrderResponse)
async def update_existing_order(
    order_id: uuid.UUID,
    body: OrderUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Partial update of order fields."""
    order = await get_order_detail(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # Designers cannot update core fields
    if current_user.role == UserRole.DESIGNER:
        raise HTTPException(status_code=403, detail="Designers cannot modify order fields directly")
        
    # Security validations are inside update_order service
    logger.info(f"Updating order {order_id} by user {current_user.email}")
    await update_order(db, order, body, current_user)
    await db.commit()
    logger.info(f"Order {order_id} update committed")
    return await get_order(order_id, current_user, db)


@router.post("/{order_id}/status", response_model=OrderResponse)
async def transition_order_status(
    order_id: uuid.UUID,
    body: StatusChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change order status with validation and history audit log."""
    order = await get_order_detail(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if current_user.role == UserRole.DESIGNER and order.assigned_designer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not assigned to this order")
        
    logger.info(f"Transitioning order {order_id} status to {body.new_status} by {current_user.email}")
    _, warnings = await change_order_status(db, order, body.new_status, current_user, body.comment)
    await db.commit()
    logger.info(f"Order {order_id} status transition committed")
    response = await get_order(order_id, current_user, db)
    # MAT-4: surface consumption warnings (currency mismatch, partial BOM
    # coverage, negative stock) on the SHIPPED-transition response only.
    response.warnings = warnings
    return response


# --- Order Items CRUD ---

@router.post("/{order_id}/items", response_model=OrderItemResponse, status_code=status.HTTP_201_CREATED)
async def add_item_to_order(
    order_id: uuid.UUID,
    body: OrderItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new item to an existing order."""
    if current_user.role == UserRole.DESIGNER:
        raise HTTPException(status_code=403, detail="Designers cannot add items")
    
    item = await add_order_item(db, order_id, body)
    await db.commit()
    return item


@router.patch("/items/{item_id}", response_model=OrderItemResponse)
async def update_item_in_order(
    item_id: uuid.UUID,
    body: OrderItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing order item."""
    if current_user.role == UserRole.DESIGNER:
        raise HTTPException(status_code=403, detail="Designers cannot update items")
    
    item = await update_order_item(db, item_id, body)
    await db.commit()
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item_from_order(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an item from an order."""
    if current_user.role == UserRole.DESIGNER:
        raise HTTPException(status_code=403, detail="Designers cannot delete items")
    
    await delete_order_item(db, item_id)


@router.get("/action/export")
async def export_orders_csv(
    status: OrderStatus | None = Query(None),
    shop_id: uuid.UUID | None = Query(None),
    search: str | None = Query(None),
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Export filtered orders as CSV. Designers cannot export."""
    filters = OrderFilters(status=status, shop_id=shop_id, search=search)
    orders, _ = await get_orders_filtered(db, 0, 10000, filters)
    
    # Generate CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Headers
    writer.writerow([
        "External ID", "Shop", "Customer", "Email", "Status", "Title", 
        "Total Price", "Currency", "Ordered At", "Shipped At", "Completed At"
    ])
    
    # Data rows
    for o in orders:
        writer.writerow([
            o.external_id,
            o.shop.name if o.shop else "",
            o.customer.full_name if o.customer else "",
            o.customer.email if o.customer else "",
            o.status.value,
            o.title,
            o.total_price,
            o.currency,
            o.ordered_at.isoformat() if o.ordered_at else "",
            o.shipped_at.isoformat() if o.shipped_at else "",
            o.completed_at.isoformat() if o.completed_at else ""
        ])
        
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders_export.csv"}
    )
