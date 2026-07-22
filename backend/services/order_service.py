"""
OrderHub CRM — Order Service
"""

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, or_, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from models.order import Order, OrderItem, OrderStatus, OrderStatusHistory, ALLOWED_TRANSITIONS
from models.user import User, UserRole
from models.customer import Customer
from models.product import Product, ProductVariant
from models.packaging import PackagingBox
from schemas.order import OrderCreate, OrderUpdate, OrderFilters, OrderItemCreate, OrderItemUpdate
from services.customer_service import upsert_customer


# Owner-only financial fields. Only OWNER may WRITE these (see update_order).
FINANCIAL_FIELDS = ("production_cost", "shipping_np_cost", "platform_fee")

# Per-order cost fields hidden on READ from users without VIEW_COSTS
# (USER-ACCESS-2). Superset of the write-gated FINANCIAL_FIELDS: it also carries
# computed_production_cost (the MAT-4 BOM cost snapshot), a read-only cost
# surface that previously leaked (LEAK 2). One list, used by BOTH the orders
# list and detail via censor_order_financials, so the two paths cannot drift
# (LEAK 1 existed because they did).
ORDER_COST_FIELDS = FINANCIAL_FIELDS + ("computed_production_cost",)
_FINANCIAL_COMMENT_RE = re.compile(r"\b(" + "|".join(FINANCIAL_FIELDS) + r"): [^,]+")


def redact_financial_comment(comment: str | None) -> str | None:
    """Redact owner-only financial values inside an audit-history comment.

    Comment format is ``"Fields updated: key: old -> new, ..."`` (see update_order);
    financial values are numeric/None with no commas, so a per-field regex on the
    ``key: value`` segment is safe. Non-financial fields are left untouched.
    """
    if not comment:
        return comment
    return _FINANCIAL_COMMENT_RE.sub(lambda m: f"{m.group(1)}: [redacted]", comment)


def censor_order_financials(data: dict, *, can_view_costs: bool) -> dict:
    """Null per-order cost fields + redact costs leaking into audit comments,
    unless the caller may view costs (USER-ACCESS-2 VIEW_COSTS).

    Mutates and returns `data` (a serialized order dict). Shared by the orders
    LIST and DETAIL endpoints so their censoring can never drift again — LEAK 1
    (list uncensored) and LEAK 2 (computed_production_cost missed) were exactly
    that drift. The status_history loop is a no-op for list rows (no such key).
    """
    if can_view_costs:
        return data
    for f in ORDER_COST_FIELDS:
        if f in data:
            data[f] = None
    for entry in data.get("status_history") or []:
        entry["comment"] = redact_financial_comment(entry.get("comment"))
    return data


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

    # USER-ACCESS-1: manager shop scoping. Empty list → in_([]) → zero rows.
    if filters.shop_ids is not None:
        conditions.append(Order.shop_id.in_(filters.shop_ids))

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
) -> tuple[Order, list[str]]:
    """Change order status with validation and history logging.

    Returns the order and any operational warnings produced by post-transition
    hooks (MAT-4 consumption on SHIPPED). Warnings are an empty list for
    transitions that produce none. Caller is responsible for committing.
    """

    if new_status == order.status:
        return order, []

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
            # USER-ACCESS-1: assignment materialises the designer's shop grant.
            from services.access_service import grant_shop_access
            await grant_shop_access(
                db, user.id, order.shop_id, actor_id=user.id, source="assignment"
            )

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

    warnings: list[str] = []
    if new_status == OrderStatus.SHIPPED:
        # MAT-4: consume materials per BOM, snapshot computed_production_cost.
        # Runs inside this transaction; caller owns the commit. Idempotent on
        # repeat SHIPPED transitions (ledger lookup); leaves existing computed
        # cost untouched on the no-op path.
        from services.order_consumption_service import consume_materials_for_order

        result = await consume_materials_for_order(db, order, user.id)
        if not result.idempotent_skip:
            order.computed_production_cost = result.computed_production_cost
            warnings = result.warnings

    return order, warnings


async def _apply_variant_snapshot(db: AsyncSession, item: OrderItem, variant_id: uuid.UUID, shop_id: uuid.UUID):
    """Fetch a variant and copy its dimensions to the OrderItem snapshot fields."""
    query = select(ProductVariant).join(Product).filter(
        ProductVariant.id == variant_id,
        Product.shop_id == shop_id
    )
    result = await db.execute(query)
    variant = result.scalar_one_or_none()

    if not variant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product variant not found or belongs to another shop"
        )

    item.product_variant_id = variant.id
    item.snapshot_weight_g = variant.weight_g
    item.snapshot_length_mm = variant.length_mm
    item.snapshot_width_mm = variant.width_mm
    item.snapshot_height_mm = variant.height_mm
    item.snapshot_title = variant.variant_name or variant.product.title


async def create_order(
    db: AsyncSession,
    data: OrderCreate,
    user: User,
    *,
    status: OrderStatus = OrderStatus.NEW,
    shipped_at: datetime | None = None,
    completed_at: datetime | None = None,
    history_comment: str = "Order manually created",
) -> Order:
    """Create an order + its opening audit row.

    Manual entry and the Shopify webhook use the defaults (status NEW, "Order
    manually created"). The SHOPIFY-BACKFILL importer passes a mapped `status`
    (+ optional shipped/completed timestamps and a descriptive `history_comment`)
    so historical orders land in the right pipeline/finance bucket. The status is
    set DIRECTLY here — the importer must NOT route through change_order_status,
    which would fire the MAT-4 live-stock consumption hook, designer
    auto-assignment, and timestamp mutation for orders that never moved through
    those states in OrderHub.
    """
    # Customupsert -> Create order -> Default History
    customer = await upsert_customer(
        db,
        data.email,
        data.full_name,
        data.shipping_country,
        phone=data.shipping_phone,
        shipping_city=data.shipping_city,
        shipping_city_ref=data.shipping_city_ref,
        shipping_warehouse_ref=data.shipping_warehouse_ref
    )

    order = Order(
        id=uuid.uuid4(),
        external_id=data.external_id,
        shop_id=data.shop_id,
        customer_id=customer.id,
        status=status,
        order_number=data.order_number,
        title=data.title,
        total_price=data.total_price,
        currency=data.currency,
        ordered_at=data.ordered_at,
        shipped_at=shipped_at,
        completed_at=completed_at,
        shipping_name=data.shipping_name,
        shipping_phone=data.shipping_phone,
        shipping_street_1=data.shipping_street_1,
        shipping_street_2=data.shipping_street_2,
        shipping_city=data.shipping_city,
        shipping_state=data.shipping_state,
        shipping_zip=data.shipping_zip,
        shipping_country=data.shipping_country,
        shipping_city_ref=data.shipping_city_ref,
        shipping_warehouse_ref=data.shipping_warehouse_ref,
        customer_note=data.customer_note,
    )
    db.add(order)
    await db.flush()
    
    # Create Items
    for item_data in data.items:
        item = OrderItem(
            id=uuid.uuid4(),
            order_id=order.id,
            title=item_data.title,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            currency=item_data.currency,
            variations=item_data.variations,
            sku=item_data.sku,
        )
        if item_data.product_variant_id:
            await _apply_variant_snapshot(db, item, item_data.product_variant_id, order.shop_id)
        db.add(item)
    
    # Initial history — one synthetic opening row. For backfilled orders this is
    # the ONLY history entry; we never fabricate a transition chain for states the
    # order never passed through here.
    history = OrderStatusHistory(
        id=uuid.uuid4(),
        order_id=order.id,
        changed_by_id=user.id,
        from_status="none",
        to_status=status.value,
        comment=history_comment
    )
    db.add(history)
    
    # Empty items for manual order (can be updated later)
    # This just ensures we have a valid Order detail response
    
    await db.flush()
    # Eager load relationships for response
    return await get_order_detail(db, order.id)


async def update_order(db: AsyncSession, order: Order, data: OrderUpdate, user: User) -> Order:
    """Partial update with detailed change tracking (audit trail)."""
    
    update_data = data.model_dump(exclude_unset=True)
    
    # Security: role check for financial fields
    if any(k in update_data for k in FINANCIAL_FIELDS) and user.role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner can modify financial fields"
        )

    # PKG-1b: packaging is shared inventory; only verify existence.
    if "packaging_id" in update_data and update_data["packaging_id"] is not None:
        box = await db.get(PackagingBox, update_data["packaging_id"])
        if not box:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Packaging box not found",
            )

    changes = []
    for key, value in update_data.items():
        old_val = getattr(order, key)
        if old_val != value:
            # Format value for comment
            display_old = str(old_val) if old_val is not None else "None"
            display_new = str(value) if value is not None else "None"
            changes.append(f"{key}: {display_old} -> {display_new}")
            setattr(order, key, value)
            
    if changes:
        # If shipping fields changed, update the customer record as well
        shipping_fields = {"shipping_phone", "shipping_city", "shipping_city_ref", "shipping_warehouse_ref"}
        if any(k in update_data for k in shipping_fields):
            # Map order field names to customer field names
            customer_updates = {}
            if "shipping_phone" in update_data: customer_updates["phone"] = update_data["shipping_phone"]
            if "shipping_city" in update_data: customer_updates["shipping_city"] = update_data["shipping_city"]
            if "shipping_city_ref" in update_data: customer_updates["shipping_city_ref"] = update_data["shipping_city_ref"]
            if "shipping_warehouse_ref" in update_data: customer_updates["shipping_warehouse_ref"] = update_data["shipping_warehouse_ref"]
            
            if customer_updates:
                await db.execute(
                    update(Customer)
                    .where(Customer.id == order.customer_id)
                    .values(**customer_updates)
                )

        # Create history entry for field mutations
        history = OrderStatusHistory(
            id=uuid.uuid4(),
            order_id=order.id,
            changed_by_id=user.id,
            from_status=order.status.value,
            to_status=order.status.value,  # Status unchanged
            comment=f"Fields updated: {', '.join(changes)}"
        )
        db.add(history)

    # USER-ACCESS-1: assigning an order to a designer materialises their shop
    # grant so order-level and shop-level access stay coherent (assignment wins).
    new_designer_id = update_data.get("assigned_designer_id")
    if new_designer_id is not None:
        assignee = await db.get(User, new_designer_id)
        if assignee and assignee.role == UserRole.DESIGNER:
            from services.access_service import grant_shop_access
            await grant_shop_access(
                db, new_designer_id, order.shop_id,
                actor_id=user.id, source="assignment",
            )

    await db.flush()
    return order


async def add_order_item(db: AsyncSession, order_id: uuid.UUID, data: OrderItemCreate) -> OrderItem:
    """Add a single item to an existing order."""
    # First get order to know the shop_id for guard
    result = await db.execute(select(Order).filter(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    item = OrderItem(
        id=uuid.uuid4(),
        order_id=order_id,
        title=data.title,
        quantity=data.quantity,
        unit_price=data.unit_price,
        currency=data.currency,
        variations=data.variations
    )
    if data.product_variant_id:
        await _apply_variant_snapshot(db, item, data.product_variant_id, order.shop_id)
    
    db.add(item)
    await db.flush()
    return item


async def update_order_item(db: AsyncSession, item_id: uuid.UUID, data: OrderItemUpdate) -> OrderItem:
    """Update an existing order item."""
    query = select(OrderItem).join(Order).filter(OrderItem.id == item_id).options(selectinload(OrderItem.order))
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Order item not found")

    update_data = data.model_dump(exclude_unset=True)
    
    # Special handling for product_variant_id to update snapshots
    if "product_variant_id" in update_data:
        v_id = update_data.pop("product_variant_id")
        if v_id:
            await _apply_variant_snapshot(db, item, v_id, item.order.shop_id)
        else:
            # Clearing the link
            item.product_variant_id = None
            item.snapshot_weight_g = None
            item.snapshot_length_mm = None
            item.snapshot_width_mm = None
            item.snapshot_height_mm = None
            item.snapshot_title = None

    for key, value in update_data.items():
        setattr(item, key, value)

    await db.flush()
    return item


async def delete_order_item(db: AsyncSession, item_id: uuid.UUID):
    """Delete an order item."""
    from sqlalchemy import delete
    await db.execute(delete(OrderItem).filter(OrderItem.id == item_id))
    await db.commit()
