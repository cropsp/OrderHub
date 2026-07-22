"""ORDER-CARD-1 Part 2 — order-item product image derivation + bulk pull.

Router functions are awaited directly with mocked dependencies (same style as
test_product_image.py / test_orders_router.py — no TestClient/conftest).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services.order_service import order_item_image_ref, attach_item_images


# ---------- pure helper: order_item_image_ref ----------


def _item(*, image_path=None, has_variant=True, has_product=True):
    item = MagicMock()
    if not has_variant:
        item.variant = None
        return item
    variant = MagicMock()
    if not has_product:
        variant.product = None
    else:
        product = MagicMock()
        product.id = uuid.uuid4()
        product.image_path = image_path
        variant.product = product
    item.variant = variant
    return item


def test_image_ref_set_when_product_has_image():
    item = _item(image_path="products/abc/def.png")
    pid, url = order_item_image_ref(item)
    assert pid == item.variant.product.id
    assert url == f"/api/products/{item.variant.product.id}/image"


def test_image_ref_none_for_custom_line_without_variant():
    assert order_item_image_ref(_item(has_variant=False)) == (None, None)


def test_image_ref_none_when_variant_has_no_product():
    assert order_item_image_ref(_item(has_product=False)) == (None, None)


def test_image_ref_none_when_product_has_no_image():
    assert order_item_image_ref(_item(image_path=None)) == (None, None)


def test_attach_item_images_populates_each_item_dict():
    imaged = _item(image_path="products/x/y.png")
    custom = _item(has_variant=False)
    order = MagicMock()
    order.items = [imaged, custom]
    data = {"items": [{"id": "a"}, {"id": "b"}]}

    attach_item_images(data, order)

    assert data["items"][0]["product_id"] == imaged.variant.product.id
    assert data["items"][0]["image_url"] == f"/api/products/{imaged.variant.product.id}/image"
    assert data["items"][1]["product_id"] is None
    assert data["items"][1]["image_url"] is None


# ---------- bulk pull endpoint: skip / count ----------


@pytest.mark.asyncio
async def test_backfill_product_images_counts_updated_no_image_and_errors():
    from routers.shops import backfill_shop_product_images

    shop = MagicMock()
    # Three eligible products (the endpoint's SELECT already excludes imaged ones).
    products = [MagicMock(id=uuid.uuid4()) for _ in range(3)]

    shop_result = MagicMock()
    shop_result.scalar_one_or_none.return_value = shop
    products_result = MagicMock()
    products_result.scalars.return_value.all.return_value = products

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[shop_result, products_result])

    # 1st stores, 2nd has no featured image (404), 3rd errors (502).
    pull = AsyncMock(side_effect=[
        None,
        HTTPException(status_code=404, detail="Shopify listing has no featured image"),
        HTTPException(status_code=502, detail="Failed to reach Shopify"),
    ])

    with patch("routers.shops.assert_shop_access", AsyncMock()), \
         patch("routers.shops.fetch_and_store_shopify_image", pull), \
         patch("routers.shops.asyncio.sleep", AsyncMock()):
        result = await backfill_shop_product_images(
            shop_id=uuid.uuid4(), current_user=MagicMock(), db=db
        )

    assert result["eligible"] == 3
    assert result["updated"] == 1
    assert result["no_image"] == 1
    assert len(result["errors"]) == 1
    assert pull.await_count == 3  # one product's failure does not abort the batch
