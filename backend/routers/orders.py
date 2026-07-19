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
from models.order import AddressValidationStatus, Order, OrderItem, OrderStatus
from models.user import User, UserRole
from schemas.address_validation import AddressInput, AddressVerdict
from schemas.order import (
    OrderFilters, OrderListResponse, OrderResponse,
    OrderCreate, OrderUpdate, StatusChangeRequest,
    BulkStatusChangeRequest, BulkStatusChangeResponse, SkippedItem,
    OrderItemCreate, OrderItemUpdate, OrderItemResponse
)
from schemas.common import PaginatedResponse
from schemas.parcel import ParcelEstimate
from routers.dependencies import (
    get_current_user, require_role, assert_order_access, assert_shop_access,
)
from services.access_service import get_shop_scope
from services.order_service import (
    get_orders_filtered, get_order_detail,
    create_order, update_order, change_order_status,
    add_order_item, update_order_item, delete_order_item,
    redact_financial_comment
)
from services.address_validation import validate_address
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
    
    # USER-ACCESS-1 shop scope: designer = assignment wins; manager = granted shops.
    if current_user.role == UserRole.DESIGNER:
        filters.assigned_designer_id = current_user.id
    elif current_user.role != UserRole.OWNER:
        scope = await get_shop_scope(db, current_user)
        if not scope.is_unrestricted:
            filters.shop_ids = list(scope.shop_ids)

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

    await assert_order_access(db, order, current_user)

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
    await assert_order_access(db, order, current_user)

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

    # USER-ACCESS-1: a manager may only create orders in shops they can access.
    await assert_shop_access(db, body.shop_id, current_user)

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

    # USER-ACCESS-1: manager must have access to this order's shop.
    await assert_order_access(db, order, current_user)

    # Security validations are inside update_order service
    logger.info(f"Updating order {order_id} by user {current_user.email}")
    await update_order(db, order, body, current_user)
    await db.commit()
    logger.info(f"Order {order_id} update committed")
    return await get_order(order_id, current_user, db)


@router.post("/bulk-status", response_model=BulkStatusChangeResponse)
async def bulk_transition_order_status(
    body: BulkStatusChangeRequest,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Apply one status to many orders, reporting the per-order outcome.

    Best-effort batch: each order runs through the same change_order_status path
    as the single-order endpoint (audit history + MAT-4 consumption included),
    and one failure does not abort the rest. A single commit closes the batch.

    Declared above the /{order_id}/... routes so no future parametrised POST can
    shadow this literal path.
    """
    updated = 0
    unchanged = 0
    skipped: list[SkippedItem] = []
    warnings: list[str] = []

    logger.info(
        f"Bulk status change to {body.new_status} for {len(body.order_ids)} order(s) "
        f"by {current_user.email}"
    )

    # USER-ACCESS-1: resolve the caller's shop scope once; a manager silently
    # skips orders in shops they cannot access (reported as skipped, not fatal).
    scope = await get_shop_scope(db, current_user)

    # dict.fromkeys dedupes while preserving the caller's order.
    for order_id in dict.fromkeys(body.order_ids):
        order = await db.get(Order, order_id)
        if order is None:
            skipped.append(SkippedItem(order_id=order_id, reason="not found"))
            continue

        if not scope.can_access(order.shop_id):
            skipped.append(SkippedItem(order_id=order_id, reason="no access to shop"))
            continue

        # change_order_status treats this as a no-op early return, which is
        # indistinguishable from success at the call site — classify it here.
        if order.status == body.new_status:
            unchanged += 1
            continue

        try:
            # SAVEPOINT per order: the SHIPPED path flushes the status change and
            # history row before the MAT-4 consumption hook runs, so a consumption
            # failure would otherwise be committed by the loop's final commit while
            # being reported as skipped.
            async with db.begin_nested():
                _, order_warnings = await change_order_status(
                    db, order, body.new_status, current_user, body.comment
                )
        except HTTPException as exc:
            skipped.append(SkippedItem(order_id=order_id, reason=str(exc.detail)))
            continue

        updated += 1
        warnings.extend(order_warnings)

    await db.commit()
    logger.info(
        f"Bulk status change committed: updated={updated} unchanged={unchanged} "
        f"skipped={len(skipped)}"
    )

    return BulkStatusChangeResponse(
        updated=updated,
        unchanged=unchanged,
        skipped=skipped,
        warnings=warnings,
    )


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

    await assert_order_access(db, order, current_user)

    logger.info(f"Transitioning order {order_id} status to {body.new_status} by {current_user.email}")
    _, warnings = await change_order_status(db, order, body.new_status, current_user, body.comment)
    await db.commit()
    logger.info(f"Order {order_id} status transition committed")
    response = await get_order(order_id, current_user, db)
    # MAT-4: surface consumption warnings (currency mismatch, partial BOM
    # coverage, negative stock) on the SHIPPED-transition response only.
    response.warnings = warnings
    return response


@router.post("/{order_id}/validate-address", response_model=AddressVerdict)
async def validate_order_address(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check an order's shipping address against the address-validation provider.

    Advisory only — never mutates the address and never blocks the order. UA,
    uncovered countries, empty addresses and an unconfigured API key all resolve
    inside the service without an API call.
    """
    order = await get_order_detail(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    await assert_order_access(db, order, current_user)

    verdict = await validate_address(db, AddressInput(
        street_1=order.shipping_street_1,
        street_2=order.shipping_street_2,
        city=order.shipping_city,
        state=order.shipping_state,
        zip=order.shipping_zip,
        country=order.shipping_country,
    ))

    # UNAVAILABLE is transient (no key, timeout, provider down) — persisting it would
    # let an outage erase a previously good verdict. Every other status is a real
    # outcome and is recorded.
    if verdict.status is not AddressValidationStatus.UNAVAILABLE:
        order.address_validation_status = verdict.status
        order.address_validation_at = verdict.validated_at
        await db.commit()

    logger.info(
        f"Address validation for order {order_id}: {verdict.status.value} "
        f"(country={order.shipping_country}) by {current_user.email}"
    )
    return verdict


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

    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    await assert_order_access(db, order, current_user)

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

    item_row = await db.get(OrderItem, item_id)
    if not item_row:
        raise HTTPException(status_code=404, detail="Item not found")
    order = await db.get(Order, item_row.order_id)
    await assert_order_access(db, order, current_user)

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

    item_row = await db.get(OrderItem, item_id)
    if not item_row:
        raise HTTPException(status_code=404, detail="Item not found")
    order = await db.get(Order, item_row.order_id)
    await assert_order_access(db, order, current_user)

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
    # USER-ACCESS-1: a manager exports only orders from shops they can access.
    if current_user.role != UserRole.OWNER:
        scope = await get_shop_scope(db, current_user)
        if not scope.is_unrestricted:
            filters.shop_ids = list(scope.shop_ids)
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
