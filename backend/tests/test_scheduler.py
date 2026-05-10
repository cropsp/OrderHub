"""BUG-9 — scheduler consumes the IMP-2 ImportResult shape from sync_shop_orders.

The scheduler used to read an int (`count > 0`); after IMP-2,
sync_shop_orders returns ImportResult. These tests pin the post-fix
contract: success log line, optional catalog-counter suffix, per-order
error warning, silence on idle.

Mocks scheduler.sync_shop_orders + scheduler.async_session_factory; no
real DB or HTTP.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from schemas.common import ImportResult


def _make_db_with_one_shop(shop, system_user):
    """Build an AsyncMock DB session whose two execute() calls return
    the System user and a single-shop list, in scheduler call order."""
    user_result = MagicMock()
    user_result.scalar_one_or_none = MagicMock(return_value=system_user)

    shops_result = MagicMock()
    shops_scalars = MagicMock()
    shops_scalars.all = MagicMock(return_value=[shop])
    shops_result.scalars = MagicMock(return_value=shops_scalars)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[user_result, shops_result])
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _session_factory_returning(db):
    """Build a sync MagicMock that, when called, returns an async
    context manager yielding `db`."""
    factory = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=None)
    factory.return_value = cm
    return factory


@pytest.mark.asyncio
async def test_run_shopify_sync_logs_success_with_catalog_counters(caplog):
    shop = MagicMock(id=uuid4())
    shop.name = "MyShop"
    system_user = MagicMock()
    db = _make_db_with_one_shop(shop, system_user)

    with patch("scheduler.async_session_factory", _session_factory_returning(db)), \
         patch("scheduler.sync_shop_orders", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = ImportResult(
            imported=2,
            skipped=0,
            errors=[],
            products_created=1,
            variants_created=3,
        )

        from scheduler import run_shopify_sync
        with caplog.at_level("INFO", logger="scheduler"):
            await run_shopify_sync()

    info_msgs = [r.getMessage() for r in caplog.records if r.levelname == "INFO"]
    assert any(
        "Synced 2 orders for shop MyShop" in m
        and "+1 product" in m
        and "+3 variants" in m
        for m in info_msgs
    ), info_msgs
    db.commit.assert_awaited_once()
    db.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_run_shopify_sync_logs_warning_on_per_order_errors(caplog):
    shop = MagicMock(id=uuid4())
    shop.name = "MyShop"
    system_user = MagicMock()
    db = _make_db_with_one_shop(shop, system_user)

    with patch("scheduler.async_session_factory", _session_factory_returning(db)), \
         patch("scheduler.sync_shop_orders", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = ImportResult(
            imported=1,
            skipped=0,
            errors=[{"external_id": "X", "error": "boom"}],
            products_created=0,
            variants_created=0,
        )

        from scheduler import run_shopify_sync
        with caplog.at_level("INFO", logger="scheduler"):
            await run_shopify_sync()

    info_msgs = [r.getMessage() for r in caplog.records if r.levelname == "INFO"]
    warn_msgs = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]

    # Partial success: success line still emitted, no catalog suffix.
    assert any(
        "Synced 1 orders for shop MyShop" in m and "(" not in m
        for m in info_msgs
    ), info_msgs
    # Per-order errors surfaced as warning naming shop + error count.
    assert any(
        "MyShop" in m and "1 per-order error" in m
        for m in warn_msgs
    ), warn_msgs
    db.commit.assert_awaited_once()
    db.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_run_shopify_sync_silent_on_zero_imported(caplog):
    shop = MagicMock(id=uuid4())
    shop.name = "MyShop"
    system_user = MagicMock()
    db = _make_db_with_one_shop(shop, system_user)

    with patch("scheduler.async_session_factory", _session_factory_returning(db)), \
         patch("scheduler.sync_shop_orders", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = ImportResult(
            imported=0,
            skipped=0,
            errors=[],
            products_created=0,
            variants_created=0,
        )

        from scheduler import run_shopify_sync
        with caplog.at_level("INFO", logger="scheduler"):
            await run_shopify_sync()

    scheduler_records = [r for r in caplog.records if r.name == "scheduler"]
    assert not any("Synced" in r.getMessage() for r in scheduler_records)
    assert not any(r.levelname == "WARNING" for r in scheduler_records)
    db.commit.assert_awaited_once()
    db.rollback.assert_not_called()
