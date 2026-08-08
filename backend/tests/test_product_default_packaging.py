"""WH-5 — `products.default_packaging_box_id`, the anchor the retro-consumption
runner resolves against.

Covers the write path (which the retro runner reads, so a silently-dropped field
would starve it) and the guard that keeps an archived box out of it. The read path
needs no test of its own: the field sits on ProductBase, so every route returning
ProductRead inherits it, and both MCP product tools are `dump()` passthroughs.

Router functions awaited directly with mocked dependencies — no TestClient
fixtures exist in this repo (see test_products_platform_gate.py).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from models.material import Material
from models.packaging import PackagingBox
from models.product import Product
from models.user import UserRole
from schemas.product import ProductCreate, ProductRead, ProductUpdate, ProductVariantCreate
from services.catalog_service import CatalogService


def _owner():
    user = MagicMock()
    user.role = UserRole.OWNER
    return user


def _variant() -> ProductVariantCreate:
    return ProductVariantCreate(
        sku="SKU-1", weight_g=100, length_mm=10, width_mm=10, height_mm=10
    )


def _box(*, is_active: bool = True):
    material = Material(
        name="Коробка 100×120×50",
        unit="шт",
        currency="UAH",
        is_active=is_active,
        category="PACKAGING",
    )
    material.id = uuid.uuid4()
    box = MagicMock(spec=PackagingBox)
    box.id = uuid.uuid4()
    box.name = material.name
    box.material = material
    box.material_is_active = is_active
    return box


def _db_returning_box(box):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=box)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    return db


# ── Schema surface ─────────────────────────────────────────


def test_the_field_is_writable_on_create_and_update_and_readable():
    """On ProductBase (not beside image_url, which is file-backed and deliberately
    read-only), so ProductCreate and ProductRead both inherit it; ProductUpdate is
    a standalone BaseModel and carries its own copy."""
    box_id = uuid.uuid4()

    assert ProductCreate(
        title="T", variants=[_variant()], default_packaging_box_id=box_id
    ).default_packaging_box_id == box_id
    assert ProductUpdate(
        default_packaging_box_id=box_id
    ).default_packaging_box_id == box_id
    assert "default_packaging_box_id" in ProductRead.model_fields


def test_an_explicit_null_clears_the_default_but_an_absent_key_does_not():
    """update_product dumps with exclude_unset=True, so these two must stay
    distinguishable — otherwise every unrelated PATCH would wipe the box."""
    cleared = ProductUpdate(default_packaging_box_id=None).model_dump(exclude_unset=True)
    untouched = ProductUpdate(title="T").model_dump(exclude_unset=True)

    assert cleared == {"default_packaging_box_id": None}
    assert "default_packaging_box_id" not in untouched


# ── Write validation ───────────────────────────────────────


@pytest.mark.asyncio
async def test_create_persists_the_default_box():
    """create_product names its columns explicitly, so a new field is silently
    dropped unless it is listed there — and the runner would then find nothing."""
    box = _box()
    db = _db_returning_box(box)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    added: list = []
    db.add = MagicMock(side_effect=added.append)

    await CatalogService(db).create_product(
        uuid.uuid4(),
        ProductCreate(
            title="Гаманець", variants=[_variant()], default_packaging_box_id=box.id
        ),
    )

    product = next(obj for obj in added if isinstance(obj, Product))
    assert product.default_packaging_box_id == box.id


@pytest.mark.asyncio
async def test_a_missing_box_is_refused():
    db = _db_returning_box(None)

    with pytest.raises(ValueError, match="not found"):
        await CatalogService(db).create_product(
            uuid.uuid4(),
            ProductCreate(
                title="T", variants=[_variant()], default_packaging_box_id=uuid.uuid4()
            ),
        )


@pytest.mark.asyncio
async def test_an_archived_box_is_refused():
    """Pointing a product's default at an archived box would manufacture WH-2's
    "archived but was still consumed" warning on every future shipment. Fail once,
    here, where a human can see it."""
    db = _db_returning_box(_box(is_active=False))

    with pytest.raises(ValueError, match="archived"):
        await CatalogService(db).create_product(
            uuid.uuid4(),
            ProductCreate(
                title="T", variants=[_variant()], default_packaging_box_id=uuid.uuid4()
            ),
        )


@pytest.mark.asyncio
async def test_clearing_the_default_skips_the_guard_entirely():
    """No box to validate, so no lookup — and clearing must never be blocked by
    the box having since been archived."""
    db = AsyncMock()
    product = MagicMock()
    service = CatalogService(db)
    service.get_product = AsyncMock(return_value=product)
    db.commit = AsyncMock()

    with patch.object(
        CatalogService, "_assert_default_box_usable", AsyncMock()
    ) as guard:
        await service.update_product(
            uuid.uuid4(), ProductUpdate(default_packaging_box_id=None)
        )

    guard.assert_not_awaited()
    assert product.default_packaging_box_id is None


@pytest.mark.asyncio
async def test_update_validates_before_assigning():
    db = _db_returning_box(None)
    service = CatalogService(db)
    service.get_product = AsyncMock(return_value=MagicMock())

    with pytest.raises(ValueError):
        await service.update_product(
            uuid.uuid4(), ProductUpdate(default_packaging_box_id=uuid.uuid4())
        )


# ── Router surfacing ───────────────────────────────────────


@pytest.mark.asyncio
async def test_both_routes_answer_400_for_an_unusable_box():
    """PATCH already mapped ValueError → 400; POST did not until WH-5. Both
    surfaces must answer the same way or the MCP tool sees two error shapes."""
    from routers.products import create_product, update_product

    schema = ProductCreate(
        title="T", variants=[_variant()], default_packaging_box_id=uuid.uuid4()
    )
    with patch("routers.products.CatalogService") as MockSvc:
        MockSvc.return_value.is_sku_taken = AsyncMock(return_value=False)
        MockSvc.return_value.create_product = AsyncMock(
            side_effect=ValueError("Packaging box X not found")
        )
        with pytest.raises(HTTPException) as exc:
            await create_product(
                shop_id=uuid.uuid4(),
                schema=schema,
                db=AsyncMock(),
                shop=MagicMock(),
                user=_owner(),
            )
    assert exc.value.status_code == 400
    assert "not found" in exc.value.detail

    with patch("routers.products.CatalogService") as MockSvc, patch(
        "routers.products._load_product_checked", AsyncMock()
    ):
        MockSvc.return_value.update_product = AsyncMock(
            side_effect=ValueError("Packaging box X is archived")
        )
        with pytest.raises(HTTPException) as exc:
            await update_product(
                id=uuid.uuid4(),
                schema=ProductUpdate(default_packaging_box_id=uuid.uuid4()),
                db=AsyncMock(),
                user=_owner(),
            )
    assert exc.value.status_code == 400
