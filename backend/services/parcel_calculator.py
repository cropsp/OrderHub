import math
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.order import Order, OrderItem
from models.packaging import PackagingBox, PackagingType
from schemas.parcel import ParcelEstimate
from schemas.packaging import PackagingBoxRead

async def calculate_parcel_estimate(db: AsyncSession, order_id: str) -> ParcelEstimate:
    # 1. Fetch order and items
    stmt = select(Order).where(Order.id == order_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    
    if not order:
        raise ValueError(f"Order {order_id} not found")

    items = order.items
    warnings = []
    
    # 2. Aggregate item data
    total_weight_g = 0
    total_volume_cm3 = 0.0
    max_length_mm = 0
    max_width_mm = 0
    total_height_mm = 0
    unlinked_items_count = 0
    
    for item in items:
        if not all([item.snapshot_weight_g, item.snapshot_length_mm, item.snapshot_width_mm, item.snapshot_height_mm]):
            unlinked_items_count += 1
            continue
            
        total_weight_g += item.snapshot_weight_g * item.quantity
        total_volume_cm3 += item.volume_cm3 * item.quantity
        max_length_mm = max(max_length_mm, item.snapshot_length_mm)
        max_width_mm = max(max_width_mm, item.snapshot_width_mm)
        total_height_mm += item.snapshot_height_mm * item.quantity

    if unlinked_items_count > 0:
        warnings.append(f"{unlinked_items_count} item(s) have no dimensions linked — calculation is partial")

    # 3. Fetch packaging
    stmt_pkg = select(PackagingBox).where(PackagingBox.shop_id == order.shop_id)
    res_pkg = await db.execute(stmt_pkg)
    all_packaging = res_pkg.scalars().all()
    
    if not all_packaging:
        warnings.append("No packaging configured for this shop — add boxes or envelopes in Inventory → Packaging")
    
    selected_pkg = None
    
    # 4. Selection Algorithm
    # Envelopes first
    envelopes = sorted(
        [p for p in all_packaging if p.packaging_type == PackagingType.ENVELOPE],
        key=lambda x: x.sort_order
    )
    
    for env in envelopes:
        weight_fits = env.max_weight_g >= total_weight_g
        thickness_fits = True
        if env.max_thickness_mm:
            thickness_fits = total_height_mm <= env.max_thickness_mm
            
        if weight_fits and thickness_fits:
            selected_pkg = env
            break
            
    # Boxes fallback
    if not selected_pkg:
        boxes = sorted(
            [p for p in all_packaging if p.packaging_type == PackagingType.BOX],
            key=lambda x: (x.inner_length_mm * x.inner_width_mm * x.inner_height_mm)
        )
        
        packing_factor = 1.25
        required_volume = total_volume_cm3 * packing_factor
        
        for box in boxes:
            box_volume = (box.inner_length_mm * box.inner_width_mm * box.inner_height_mm) / 1000.0
            if box_volume >= required_volume and box.max_weight_g >= total_weight_g:
                selected_pkg = box
                break

    if all_packaging and not selected_pkg:
        warnings.append("Order does not fit any available packaging")

    # 5. Final dimensions and weights
    if selected_pkg:
        parcel_l = selected_pkg.inner_length_mm
        parcel_w = selected_pkg.inner_width_mm
        parcel_h = selected_pkg.inner_height_mm
        total_weight_g += selected_pkg.tare_weight_g
    else:
        # Fallback to item-based dimensions
        parcel_l = max_length_mm
        parcel_w = max_width_mm
        parcel_h = total_height_mm

    # Volumetric weight: (L_cm * W_cm * H_cm) / 4 = grams
    volumetric_weight_g = int((parcel_l / 10.0 * parcel_w / 10.0 * parcel_h / 10.0) / 4.0) * 10 # Round to nearest 10 for safety?
    # Wait, SKILL.md says L_cm * W_cm * H_cm / 4. 
    # Example: 20x20x20cm box = 8000 / 4 = 2000g = 2kg.
    # NP uses 4000 divisor for kg. 8000 / 4000 = 2kg. Matches.
    volumetric_weight_g = int((parcel_l / 10.0 * parcel_w / 10.0 * parcel_h / 10.0) / 4.0)
    
    chargeable_weight_g = max(total_weight_g, volumetric_weight_g)

    return ParcelEstimate(
        total_weight_g=total_weight_g,
        total_volume_cm3=total_volume_cm3,
        selected_packaging=PackagingBoxRead.from_orm(selected_pkg) if selected_pkg else None,
        packaging_type=selected_pkg.packaging_type.value if selected_pkg else None,
        parcel_length_mm=parcel_l,
        parcel_width_mm=parcel_w,
        parcel_height_mm=parcel_h,
        volumetric_weight_g=volumetric_weight_g,
        chargeable_weight_g=chargeable_weight_g,
        unlinked_items_count=unlinked_items_count,
        warnings=warnings
    )
