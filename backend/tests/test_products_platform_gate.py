"""CAT-VIS-1 — Platform gating on /api/shops/{shop_id}/products endpoints.

The list endpoint must accept any platform (Etsy/Shopify/manual) — access is
gated only by get_shop_for_user. The create + bulk-CSV endpoints must keep
require_platform(MANUAL) so platform-driven catalogs can't be polluted by
manual writes.
"""
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from routers.products import list_products
from routers.dependencies import require_platform


def _shop(platform):
    s = MagicMock()
    s.platform = MagicMock()
    s.platform.value = platform
    return s


@pytest.mark.asyncio
async def test_list_products_accepts_etsy_shop():
    shop_id = uuid4()
    db = AsyncMock()
    with patch("routers.products.CatalogService") as MockSvc:
        MockSvc.return_value.get_products = AsyncMock(return_value=[])
        result = await list_products(
            shop_id=shop_id, is_active=True, db=db, shop=_shop("etsy")
        )
    assert result == []
    MockSvc.return_value.get_products.assert_awaited_once_with(shop_id, is_active=True)


@pytest.mark.asyncio
async def test_list_products_accepts_shopify_shop():
    shop_id = uuid4()
    db = AsyncMock()
    with patch("routers.products.CatalogService") as MockSvc:
        MockSvc.return_value.get_products = AsyncMock(return_value=[])
        result = await list_products(
            shop_id=shop_id, is_active=True, db=db, shop=_shop("shopify")
        )
    assert result == []


@pytest.mark.asyncio
async def test_list_products_accepts_manual_shop():
    shop_id = uuid4()
    db = AsyncMock()
    with patch("routers.products.CatalogService") as MockSvc:
        MockSvc.return_value.get_products = AsyncMock(return_value=[])
        result = await list_products(
            shop_id=shop_id, is_active=True, db=db, shop=_shop("manual")
        )
    assert result == []


@pytest.mark.asyncio
async def test_require_platform_manual_blocks_etsy():
    """POST endpoints (create / bulk-csv) keep this gate — etsy must 403."""
    checker = require_platform("manual")
    with pytest.raises(HTTPException) as exc:
        await checker(shop=_shop("etsy"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_platform_manual_blocks_shopify():
    checker = require_platform("manual")
    with pytest.raises(HTTPException) as exc:
        await checker(shop=_shop("shopify"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_platform_manual_allows_manual():
    checker = require_platform("manual")
    manual = _shop("manual")
    result = await checker(shop=manual)
    assert result is manual
