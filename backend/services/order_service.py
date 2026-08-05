"""
OrderHub CRM — Order Service
"""

import logging
import re
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Date, cast, select, func, or_, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from models.order import Order, OrderItem, OrderStatus, OrderStatusHistory, ALLOWED_TRANSITIONS
from models.shop import Shop
from models.user import User, UserRole
from models.customer import Customer
from models.product import Product, ProductVariant
from models.packaging import PackagingBox
from schemas.order import OrderCreate, OrderUpdate, OrderFilters, OrderItemCreate, OrderItemUpdate
from services.customer_service import upsert_customer

logger = logging.getLogger(__name__)


# Owner-only financial fields. Only OWNER may WRITE these (see update_order).
FINANCIAL_FIELDS = ("production_cost", "shipping_np_cost", "platform_fee")

# Per-order cost fields hidden on READ from users without VIEW_COSTS
# (USER-ACCESS-2). Superset of the write-gated FINANCIAL_FIELDS: it also carries
# computed_production_cost (the MAT-4 BOM cost snapshot), a read-only cost
# surface that previously leaked (LEAK 2). One list, used by BOTH the orders
# list and detail via censor_order_financials, so the two paths cannot drift
# (LEAK 1 existed because they did).
# FX-CONVERSION adds the provenance of computed_production_cost. The basis is a
# cost figure outright (the same money, pre-conversion), and the rate is censored
# with it: showing "44.6395" next to a nulled cost invites reconstruction and is
# incoherent besides — a caller who may not see the cost has no use for its rate.
# Classified `cost` in test_money_field_completeness, which then requires exactly
# this list to match, so the censor set cannot drift from the classification.
ORDER_COST_FIELDS = FINANCIAL_FIELDS + (
    "computed_production_cost",
    "cogs_fx_rate",
    "cogs_basis_amount",
)
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


def compute_platform_fee(total_price, fee_percent) -> Decimal | None:
    """The order's platform fee: `total_price × fee_percent / 100` (SHOP-FEE-1).

    `fee_percent` is the shop's total effective transaction rate (see
    `models.shop.Shop.fee_percent`). None means the shop has no rate configured,
    and the answer is None — NOT 0.00 — so `platform_fee` stays NULL and the
    order remains eligible for a later backfill. A configured rate of 0 does
    return `Decimal("0.00")`: that shop has been priced, at zero.

    The base is `Order.total_price`, the full customer charge (inclusive of
    shipping and tax, gross of refunds) — the amount the merchant of record
    actually receives and commissions. ORDER-SHIPPING-1 added
    `shipping_revenue` / `discount_total` / `tax_total`, so a narrower base is
    now expressible; the gross base is kept DELIBERATELY. The channel commissions
    the whole charge, and re-basing the fee would silently re-price every order
    already in the P&L.

    Both arguments go through `Decimal(str(x))` so a float total never
    contaminates the result with binary-float error, and a non-numeric argument
    raises `InvalidOperation` rather than silently yielding a wrong number.
    Quantized ONCE at the end, ROUND_HALF_UP — the same convention as the
    consumption/BOM cost paths.
    """
    if fee_percent is None:
        return None
    total = Decimal(str(total_price))
    percent = Decimal(str(fee_percent))
    return (total * percent / Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


async def backfill_platform_fees(
    db: AsyncSession,
    shop: Shop,
    *,
    since: date | None = None,
    until: date | None = None,
    dry_run: bool = True,
) -> dict:
    """One-time re-pricing of existing orders that never got a fee (SHOP-FEE-1).

    The sync only ever prices an order at CREATION and never revisits an existing
    row, so without this every order imported before the shop's rate was set
    keeps `platform_fee IS NULL` forever and its months stay overstated in the
    P&L. This is the explicit, operator-driven catch-up for that history.

    Eligibility, deliberately identical to the sync-time rule so the two paths
    cannot drift:
      - `platform_fee IS NULL` — a fee a human entered is NEVER overwritten, and
        an auto fee already written is never recomputed at a newer rate (an
        order's fee is frozen at its creation rate, like `cogs_fx_rate`).
      - status != CANCELLED — cancelled orders are outside REVENUE_STATUSES, so a
        fee there is inert in the P&L but wrong on the order card.

    `since`/`until` bound the run by `COALESCE(shipped_at, ordered_at)` — the same
    expression finance buckets by — so the reported total reconciles against the
    finance-page delta and lines up with partner settlement periods. Leaving them
    unset re-prices the shop's whole history.

    Not platform-gated: `fee_percent` is generic shop config, and only shops the
    operator has actually given a rate are reachable here at all.

    Returns per-currency fee totals split by whether the order is already in the
    P&L (SHIPPED/COMPLETED) or still pending, so the operator can see the
    immediate impact separately from what is coming. Writes no per-order history
    rows — the endpoint call and its dry-run report are the record, as with
    `backfill_order_numbers`.
    """
    empty = {
        "matched": 0,
        "affects_pnl_now": 0,
        "pending": 0,
        "fee_total_by_currency": {},
        "fee_total_pnl_now_by_currency": {},
        "updated": 0,
        "dry_run": dry_run,
    }
    if shop.fee_percent is None:
        return empty

    date_expr = func.coalesce(Order.shipped_at, Order.ordered_at)
    conditions = [
        Order.shop_id == shop.id,
        Order.platform_fee.is_(None),
        Order.status != OrderStatus.CANCELLED,
    ]
    if since is not None:
        conditions.append(cast(date_expr, Date) >= since)
    if until is not None:
        conditions.append(cast(date_expr, Date) <= until)

    result = await db.execute(
        select(Order.id, Order.total_price, Order.currency, Order.status).where(*conditions)
    )
    rows = result.all()
    if not rows:
        return empty

    revenue_statuses = (OrderStatus.SHIPPED, OrderStatus.COMPLETED)
    fee_by_currency: dict[str, Decimal] = {}
    fee_by_currency_pnl: dict[str, Decimal] = {}
    affects_pnl_now = 0
    fees: list[tuple[uuid.UUID, Decimal]] = []

    for row in rows:
        fee = compute_platform_fee(row.total_price, shop.fee_percent)
        fees.append((row.id, fee))
        currency = row.currency or "USD"
        fee_by_currency[currency] = fee_by_currency.get(currency, Decimal("0")) + fee
        if row.status in revenue_statuses:
            affects_pnl_now += 1
            fee_by_currency_pnl[currency] = (
                fee_by_currency_pnl.get(currency, Decimal("0")) + fee
            )

    updated = 0
    if not dry_run:
        for order_id, fee in fees:
            res = await db.execute(
                update(Order)
                # The NULL guard is repeated here, not just in the SELECT above,
                # so a fee entered between the two can never be overwritten.
                .where(Order.id == order_id, Order.platform_fee.is_(None))
                .values(platform_fee=fee)
            )
            updated += res.rowcount or 0
        await db.flush()

    logger.info(
        "Platform-fee backfill for shop %s (rate=%s, dry_run=%s): matched=%d "
        "affects_pnl_now=%d updated=%d",
        shop.id, shop.fee_percent, dry_run, len(rows), affects_pnl_now, updated,
    )

    return {
        "matched": len(rows),
        "affects_pnl_now": affects_pnl_now,
        "pending": len(rows) - affects_pnl_now,
        "fee_total_by_currency": {c: float(v) for c, v in fee_by_currency.items()},
        "fee_total_pnl_now_by_currency": {
            c: float(v) for c, v in fee_by_currency_pnl.items()
        },
        "updated": updated,
        "dry_run": dry_run,
    }


def order_item_image_ref(item: OrderItem) -> tuple[uuid.UUID | None, str | None]:
    """Resolve an order item's linked-product image as (product_id, image_url).

    Mirrors the products serializer convention (routers/products.py `_project_product`):
    image_url is `/api/products/{id}/image` when the linked product has an image,
    else None. Custom lines (no variant) and products without an image → (None, None).

    Requires `item.variant.product` to be eager-loaded (get_order_detail does so).
    """
    variant = item.variant
    product = variant.product if variant else None
    if product and product.image_path:
        return product.id, f"/api/products/{product.id}/image"
    return None, None


def attach_item_images(data: dict, order: Order) -> dict:
    """Populate each serialized order item's `product_id` + `image_url` from the
    eager-loaded ORM items (index-aligned with `data['items']`). Mutates + returns
    `data`. Images are not cost-bearing, so this is independent of cost censoring.
    """
    for item_data, item_orm in zip(data.get("items") or [], order.items):
        product_id, image_url = order_item_image_ref(item_orm)
        item_data["product_id"] = product_id
        item_data["image_url"] = image_url
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
        # ORDER-CARD-1 Part 2: eager-load item → variant → product so the response
        # can carry each item's product image_url without an N+1 (2 extra queries).
        selectinload(Order.items)
        .selectinload(OrderItem.variant)
        .selectinload(ProductVariant.product),
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
        from services import fx_service
        from services.order_consumption_service import consume_materials_for_order

        # FX-CONVERSION: resolve the rate HERE, at the transaction boundary, and
        # pass it down. Keeping the lookup out of the consumption fold means that
        # path issues no extra queries, and lets the parity test drive booking and
        # preview with one identical rate. resolve() never calls NBU — a fetch on
        # this path could roll back a transition whose TTN already exists at NP.
        fx = await fx_service.resolve(db)

        result = await consume_materials_for_order(db, order, user.id, fx=fx)
        if not result.idempotent_skip:
            # All four move together. Writing the rate outside this guard would
            # stamp today's rate onto a cost booked months ago whenever an order
            # goes SHIPPED -> IN_PROGRESS -> SHIPPED, and the resulting
            # (cost, rate) pair would look like data rather than a bug.
            order.computed_production_cost = result.computed_production_cost
            order.cogs_fx_rate = result.fx_rate_used
            order.cogs_basis_amount = result.basis_amount
            order.cogs_basis_currency = result.basis_currency
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
    platform_fee: Decimal | None = None,
    shipping_revenue: Decimal | None = None,
    discount_total: Decimal | None = None,
    tax_total: Decimal | None = None,
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

    `platform_fee` (SHOP-FEE-1) is keyword-only and deliberately NOT part of
    `OrderCreate`: that schema is the public request body for POST /api/orders,
    which has no owner gate on FINANCIAL_FIELDS (the gate lives in update_order),
    so putting a cost field there would open a non-owner write path. Importers
    pass it explicitly; manual order entry leaves it None.

    `shipping_revenue` / `discount_total` / `tax_total` (ORDER-SHIPPING-1) are
    keyword-only for a DIFFERENT reason — they are revenue, not costs, so the
    non-owner-write argument above does not apply. The invariant being protected
    is that these three are only ever written from a channel payload. They are
    facts reported by Shopify, and `OrderCreate` is the public POST body, where a
    manual creator could invent a shipping figure indistinguishable from a
    captured one. They are absent from `OrderUpdate` for the same reason: there
    is no manual write path at all. NULL means unknown, never 0.00.
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
        platform_fee=platform_fee,
        shipping_revenue=shipping_revenue,
        discount_total=discount_total,
        tax_total=tax_total,
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
