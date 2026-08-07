"""
OrderHub CRM — BOM Service

MAT-3: read + replace recipes; compute theoretical unit cost grouped by
material currency. FX-CONVERSION: optionally also express that cost in one
target currency, so a UAH recipe can be previewed in the USD a shop sells in.

The router owns the commit boundary. `replace_bom` runs DELETE-all + bulk
INSERT inside one transaction (no diff-patch — BOM size is small, 3-10 rows
typically; design doc §5.3 + task.md OQ #3).

Inactive-material policy (task.md OQ #4): PUT rejects new BomItems whose
material_id points to a soft-deleted Material. BomItems that were already in
the recipe before the PUT can keep referencing the now-inactive material —
historical recipes stay intact.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from models.bom import BomItem
from models.material import Material
from schemas.bom import (
    BomCostBreakdown,
    BomCostConverted,
    BomCostEnvelope,
    BomItemCreate,
    BomItemRead,
)
from services.fx_service import FxRates, normalize_currency


async def get_bom(
    db: AsyncSession, *, product_id: uuid.UUID
) -> tuple[list[BomItem], bool]:
    """Return BomItems for a product (joined material), and a flag indicating
    whether any line references a soft-deleted Material."""
    stmt = (
        select(BomItem)
        .options(joinedload(BomItem.material))
        .join(Material, BomItem.material_id == Material.id)
        .where(BomItem.product_id == product_id)
        .order_by(Material.name)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    has_inactive = any(not bi.material.is_active for bi in items)
    return items, has_inactive


async def compute_bom_cost(
    db: AsyncSession,
    *,
    product_id: uuid.UUID,
    target_currency: str | None = None,
    fx: FxRates | None = None,
) -> BomCostEnvelope:
    """SUM(qty_per_unit * waste_factor * current_unit_cost) grouped by currency,
    plus — when `target_currency` is given — the whole recipe in that currency.

    BOM-WASTE-1: each line carries the material's own waste allowance
    (`1 + waste_percent/100`), exactly as order_consumption_service.py does when
    it books COGS on shipment. Before this, the reviewed number and the booked
    number diverged silently as soon as waste > 0.

    Folded in Python rather than a DB-side SUM so the arithmetic is the *same
    Decimal operations in the same order* as the consumption path — parity to
    the kopeck is then structural, not a claim about Postgres numeric scale.
    A BOM is 3-10 rows, so materialising them is free.

    Rounding mirrors the consumption path: accumulate un-rounded, quantize ONCE,
    ROUND_HALF_UP — for the per-currency basis rows AND for the converted total,
    which is summed across converted-but-un-rounded buckets. Note this means the
    sum of the individually-rounded `BomItemRead.line_cost` values may differ
    from these totals by a kopeck. That is deliberate — the total is
    authoritative because it is what shipment books.

    FX-CONVERSION. `target_currency` is explicit rather than derived from the
    product's shop: `Shop` has no currency column, and inventing one would key
    the preview off a different source than the booking (which uses
    `order.currency`), re-opening the preview-vs-booked divergence BOM-WASTE-1
    just closed. `fx` is passed in by the caller for the same reason the
    consumption service takes it — so one resolved rate can drive both sides and
    the parity test can prove they agree.

    Conversion is all-or-nothing, matching the booking path: if any basis
    currency cannot be converted, `converted` is None and the caller sees the
    honest per-currency basis instead of a partial total.
    """
    fx = fx or FxRates.unavailable()

    stmt = (
        select(
            Material.currency,
            BomItem.qty_per_unit,
            Material.current_unit_cost,
            Material.waste_percent,
        )
        .join(Material, BomItem.material_id == Material.id)
        .where(BomItem.product_id == product_id)
        .order_by(Material.currency)
    )
    result = await db.execute(stmt)

    totals: dict[str, Decimal] = {}
    for currency, qty_per_unit, unit_cost, waste_percent in result.all():
        waste_factor = Decimal("1") + (waste_percent / Decimal("100"))
        currency = normalize_currency(currency)
        totals[currency] = (
            totals.get(currency, Decimal("0"))
            + qty_per_unit * waste_factor * unit_cost
        )

    basis = [
        BomCostBreakdown(
            currency=currency,
            amount=amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )
        for currency, amount in totals.items()
    ]

    return BomCostEnvelope(
        basis=basis,
        converted=_convert_totals(totals, target_currency, fx),
    )


def _convert_totals(
    totals: dict[str, Decimal], target_currency: str | None, fx: FxRates
) -> BomCostConverted | None:
    """Fold the per-currency basis into one target currency, or None."""
    target = normalize_currency(target_currency)
    if not target or not totals:
        return None
    if not all(fx.can_convert(frm=c, to=target) for c in totals):
        return None

    converted_total = Decimal("0")
    rate_used: Decimal | None = None
    for currency, amount in totals.items():
        converted_total += fx.convert(amount, frm=currency, to=target)
        rate = fx.rate_for(frm=currency, to=target)
        if rate is not None:
            rate_used = rate

    if rate_used is None:
        # Everything was already in the target currency — reporting a "converted"
        # figure with no rate would imply a conversion that never happened.
        return None

    return BomCostConverted(
        currency=target,
        converted_cost=converted_total.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
        uah_per_usd=rate_used,
        rate_date=fx.rate_date,
        rate_source=fx.source,
    )


async def replace_bom(
    db: AsyncSession,
    *,
    product_id: uuid.UUID,
    items: Iterable[BomItemCreate],
) -> tuple[list[BomItem], bool]:
    """Transactional DELETE-all + bulk INSERT. Caller commits.

    Validates that every input material_id exists, and rejects any that point
    to an inactive Material UNLESS that material_id was already in the prior
    recipe (grandfathered for historical preservation).
    """
    items = list(items)

    # 1. Read prior recipe so we know which material_ids are grandfathered.
    existing_q = await db.execute(
        select(BomItem.material_id).where(BomItem.product_id == product_id)
    )
    existing_ids = set(existing_q.scalars().all())

    # 2. Validate every input material_id exists; reject inactive unless grandfathered.
    if items:
        input_ids = [item.material_id for item in items]
        materials_q = await db.execute(
            select(Material).where(Material.id.in_(input_ids))
        )
        by_id: dict[uuid.UUID, Material] = {m.id: m for m in materials_q.scalars().all()}
        for item in items:
            mat = by_id.get(item.material_id)
            if mat is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Material {item.material_id} does not exist",
                )
            if not mat.is_active and item.material_id not in existing_ids:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Material '{mat.name}' is discontinued; "
                        "restore it or pick an active replacement"
                    ),
                )
            # WH-1: a box is one per PARCEL, not one per product — an order of three
            # items ships in one box — so packaging has no place in a per-product
            # recipe (DESIGN §2.4); the parcel calculator + order.packaging_id are
            # where it belongs. Enforced here rather than only in the picker because
            # this is the single write path for the UI and for all three MCP BOM
            # tools. Grandfathered like inactive materials, so a recipe that already
            # contains one stays editable.
            if mat.category == "PACKAGING" and item.material_id not in existing_ids:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"'{mat.name}' is packaging; packaging is attached per parcel "
                        "(order packaging / parcel calculator), not per product recipe"
                    ),
                )

    # 3. Replace-all.
    await db.execute(delete(BomItem).where(BomItem.product_id == product_id))
    for item in items:
        db.add(
            BomItem(
                product_id=product_id,
                material_id=item.material_id,
                qty_per_unit=item.qty_per_unit,
                notes=item.notes,
            )
        )
    await db.flush()

    return await get_bom(db, product_id=product_id)


def project_bom_item(item: BomItem) -> BomItemRead:
    """Hydrate the read schema from a BomItem with its joined Material."""
    mat = item.material
    return BomItemRead(
        id=item.id,
        product_id=item.product_id,
        material_id=item.material_id,
        qty_per_unit=item.qty_per_unit,
        notes=item.notes,
        material_name=mat.name,
        material_unit=mat.unit,
        material_currency=mat.currency,
        material_current_unit_cost=mat.current_unit_cost,
        material_waste_percent=mat.waste_percent,
        material_is_active=mat.is_active,
        # WH-1. `is not False` rather than the raw value: the column is NOT NULL in
        # the DB, but a Material that has not been flushed yet reads None (column
        # defaults apply at INSERT), and None on a `bool` field would raise a
        # ValidationError and 500 the BOM read. Same normalisation as the
        # consumption path — unset means tracked.
        material_is_stock_tracked=mat.is_stock_tracked is not False,
    )
