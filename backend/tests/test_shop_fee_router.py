"""SHOP-FEE-1 — the shops-router surface for fee_percent.

Two things under test: that the rate is hidden from callers who may not see
costs (it reconstructs platform_fee exactly when multiplied by the never-censored
total_price), and the backfill endpoint's guards.

Router functions are awaited directly with mock sessions, matching the style in
test_shop_access.py — the role dependency itself is declarative and is covered by
test_route_scope_completeness.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from models.shop import Shop, ShopPlatform
from models.user import UserRole
from routers.shops import backfill_shop_platform_fees, get_shop, list_shops
from schemas.shop import ShopPlatformFeeBackfillRequest
from services.access_service import CapabilitySet


# ── helpers ────────────────────────────────────────────────


def _shop(fee_percent=Decimal("8.00")):
    now = datetime.now(timezone.utc)
    shop = Shop(
        id=uuid4(),
        name="Lamamarka",
        platform=ShopPlatform.SHOPIFY,
        fee_percent=fee_percent,
        color="#6366F1",
        is_active=True,
        np_default_weight_kg=0.5,
        np_default_volume_m3=0.004,
        np_default_payer_type="Sender",
        np_default_payment_method="Cash",
        last_synced_at=None,
    )
    shop.created_at = now
    shop.updated_at = now
    return shop


def _user(role=UserRole.OWNER):
    u = MagicMock()
    u.role = role
    u.id = uuid4()
    return u


def _db_returning_shops(shops):
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = shops
    db.execute = AsyncMock(return_value=result)
    return db


def _db_returning_shop(shop):
    db = MagicMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = shop
    result.scalar.return_value = 0
    db.execute = AsyncMock(return_value=result)
    return db


def _caps(can_view_costs):
    caps = MagicMock(spec=CapabilitySet)
    caps.has.return_value = can_view_costs
    return caps


# ── fee_percent visibility ─────────────────────────────────


@pytest.mark.asyncio
async def test_list_shops_exposes_fee_percent_to_cost_viewers():
    shop = _shop(Decimal("8.00"))
    db = _db_returning_shops([shop])

    with patch("routers.shops.get_shop_scope",
               AsyncMock(return_value=MagicMock(is_unrestricted=True))), \
         patch("routers.shops.get_capabilities", AsyncMock(return_value=_caps(True))):
        out = await list_shops(current_user=_user(), db=db)

    assert out[0].fee_percent == Decimal("8.00")


@pytest.mark.asyncio
async def test_list_shops_hides_fee_percent_without_view_costs():
    """rate x total_price reconstructs platform_fee, and total_price is never
    censored — so a designer reading the sidebar shop list must not get the rate."""
    shop = _shop(Decimal("8.00"))
    db = _db_returning_shops([shop])

    with patch("routers.shops.get_shop_scope",
               AsyncMock(return_value=MagicMock(is_unrestricted=True))), \
         patch("routers.shops.get_capabilities", AsyncMock(return_value=_caps(False))):
        out = await list_shops(current_user=_user(UserRole.DESIGNER), db=db)

    assert out[0].fee_percent is None
    # The rest of the shop is untouched — this is a field-level null, not a 403.
    assert out[0].name == "Lamamarka"


@pytest.mark.asyncio
async def test_get_shop_hides_fee_percent_without_view_costs():
    """Detail must censor identically to list. The order list/detail pair drifted
    exactly this way once (LEAK 1)."""
    shop = _shop(Decimal("8.00"))
    db = _db_returning_shop(shop)

    with patch("routers.shops.assert_shop_access", AsyncMock()), \
         patch("routers.shops.get_capabilities", AsyncMock(return_value=_caps(False))):
        out = await get_shop(shop.id, current_user=_user(UserRole.DESIGNER), db=db)

    assert out.fee_percent is None


@pytest.mark.asyncio
async def test_get_shop_exposes_fee_percent_to_cost_viewers():
    shop = _shop(Decimal("8.00"))
    db = _db_returning_shop(shop)

    with patch("routers.shops.assert_shop_access", AsyncMock()), \
         patch("routers.shops.get_capabilities", AsyncMock(return_value=_caps(True))):
        out = await get_shop(shop.id, current_user=_user(), db=db)

    assert out.fee_percent == Decimal("8.00")


# ── backfill endpoint guards ───────────────────────────────


@pytest.mark.asyncio
async def test_backfill_rejects_shop_without_a_rate():
    """422 rather than a silent no-op: the operator asked for a re-price and needs
    to be told why nothing happened."""
    db = _db_returning_shop(_shop(fee_percent=None))

    with patch("routers.shops.find_settlements_overlapping_period",
               AsyncMock(return_value=[])):
        with pytest.raises(HTTPException) as exc:
            await backfill_shop_platform_fees(
                uuid4(), ShopPlatformFeeBackfillRequest(), current_user=_user(), db=db
            )

    assert exc.value.status_code == 422
    assert "fee_percent" in exc.value.detail


@pytest.mark.asyncio
async def test_backfill_404_for_unknown_shop():
    db = _db_returning_shop(None)

    with pytest.raises(HTTPException) as exc:
        await backfill_shop_platform_fees(
            uuid4(), ShopPlatformFeeBackfillRequest(), current_user=_user(), db=db
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_backfill_dry_run_rolls_back():
    shop = _shop()
    db = _db_returning_shop(shop)

    with patch("routers.shops.find_settlements_overlapping_period",
               AsyncMock(return_value=[])), \
         patch("routers.shops.backfill_platform_fees",
               AsyncMock(return_value={"matched": 3, "updated": 0, "dry_run": True})):
        out = await backfill_shop_platform_fees(
            shop.id,
            ShopPlatformFeeBackfillRequest(dry_run=True),
            current_user=_user(),
            db=db,
        )

    db.rollback.assert_awaited_once()
    assert out["status"] == "success"
    assert out["fee_percent"] == 8.0


@pytest.mark.asyncio
async def test_backfill_real_run_does_not_roll_back():
    shop = _shop()
    db = _db_returning_shop(shop)

    with patch("routers.shops.find_settlements_overlapping_period",
               AsyncMock(return_value=[])), \
         patch("routers.shops.backfill_platform_fees",
               AsyncMock(return_value={"matched": 3, "updated": 3, "dry_run": False})):
        await backfill_shop_platform_fees(
            shop.id,
            ShopPlatformFeeBackfillRequest(dry_run=False),
            current_user=_user(),
            db=db,
        )

    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_unbounded_backfill_still_checks_settlements():
    """find_settlements_overlapping_period predicates period_end >= since, so
    passing None would report zero overlaps precisely when the window is
    unbounded and the settlement exposure is at its largest."""
    shop = _shop()
    db = _db_returning_shop(shop)
    finder = AsyncMock(return_value=[])

    with patch("routers.shops.find_settlements_overlapping_period", finder), \
         patch("routers.shops.backfill_platform_fees",
               AsyncMock(return_value={"matched": 0, "updated": 0, "dry_run": True})):
        await backfill_shop_platform_fees(
            shop.id,
            ShopPlatformFeeBackfillRequest(since=None, until=None),
            current_user=_user(),
            db=db,
        )

    assert finder.await_args.args[2] == date.min


@pytest.mark.asyncio
async def test_backfill_passes_window_through_to_the_service():
    shop = _shop()
    db = _db_returning_shop(shop)
    runner = AsyncMock(return_value={"matched": 0, "updated": 0, "dry_run": True})

    with patch("routers.shops.find_settlements_overlapping_period",
               AsyncMock(return_value=[])), \
         patch("routers.shops.backfill_platform_fees", runner):
        await backfill_shop_platform_fees(
            shop.id,
            ShopPlatformFeeBackfillRequest(since=date(2026, 1, 1), until=date(2026, 6, 30)),
            current_user=_user(),
            db=db,
        )

    assert runner.await_args.kwargs["since"] == date(2026, 1, 1)
    assert runner.await_args.kwargs["until"] == date(2026, 6, 30)


def test_backfill_request_rejects_inverted_range():
    with pytest.raises(ValueError):
        ShopPlatformFeeBackfillRequest(since=date(2026, 6, 30), until=date(2026, 1, 1))
