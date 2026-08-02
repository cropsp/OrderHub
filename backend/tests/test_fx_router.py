"""FX-CONVERSION — router tests for /api/settings/fx.

Calls the endpoint coroutines directly, mirroring test_app_settings_router.py.

Scope decision under test: these are OWNER-only, like every other /api/settings
route. The rate re-prices every subsequent shipment globally, so it is owner
business config. Rate PROVENANCE is exposed separately alongside the cost it
explains (order detail, BOM preview) under VIEW_COSTS — that is commits B and C.
"""
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from models.app_setting import (
    FX_RATE_DATE,
    FX_SOURCE_URL,
    FX_UAH_PER_USD_CACHED,
    FX_UAH_PER_USD_OVERRIDE,
    AppSetting,
)
from models.user import UserRole
from routers.app_settings import (
    clear_fx_override,
    get_fx_settings,
    set_fx_settings,
)
from routers.dependencies import require_role
from schemas.fx import FxSettingsUpdate
from services import fx_service


def _make_user(role=UserRole.OWNER):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.email = "owner@example.com"
    return user


def _db(values: dict[str, str], *, row=None):
    result = MagicMock()
    result.all.return_value = list(values.items())
    result.scalar_one_or_none.return_value = row
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


# ─── Read ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_reports_the_effective_rate_and_its_source():
    db = _db({FX_UAH_PER_USD_CACHED: "44.6395", FX_RATE_DATE: "2026-08-03"})

    result = await get_fx_settings(_make_user(), db)

    assert result.uah_per_usd_effective == Decimal("44.6395")
    assert result.source == "nbu"
    assert result.source_url == fx_service.NBU_DEFAULT_URL


@pytest.mark.asyncio
async def test_get_shows_both_inputs_so_clearing_is_predictable():
    """The UI must be able to say what clearing the override reverts TO, before
    the owner clears it."""
    db = _db(
        {FX_UAH_PER_USD_OVERRIDE: "41.5", FX_UAH_PER_USD_CACHED: "44.6395"}
    )

    result = await get_fx_settings(_make_user(), db)

    assert result.uah_per_usd_effective == Decimal("41.5")
    assert result.source == "manual"
    assert result.uah_per_usd_override == Decimal("41.5")
    assert result.uah_per_usd_cached == Decimal("44.6395")


@pytest.mark.asyncio
async def test_get_is_unset_when_nothing_is_configured():
    result = await get_fx_settings(_make_user(), _db({}))

    assert result.uah_per_usd_effective is None
    assert result.source is None


@pytest.mark.asyncio
async def test_a_corrupted_stored_value_does_not_500_the_settings_page():
    result = await get_fx_settings(_make_user(), _db({FX_UAH_PER_USD_OVERRIDE: "junk"}))

    assert result.uah_per_usd_effective is None
    assert result.uah_per_usd_override is None


# ─── Write ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_put_sets_the_manual_override():
    db = _db({}, row=None)
    owner = _make_user()

    await set_fx_settings(
        FxSettingsUpdate(uah_per_usd_override=Decimal("41.5")), owner, db
    )

    written = [c[0][0] for c in db.add.call_args_list if isinstance(c[0][0], AppSetting)]
    assert written[0].key == FX_UAH_PER_USD_OVERRIDE
    assert written[0].value == "41.5"
    assert written[0].updated_by_id == owner.id
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_put_rejects_an_override_outside_the_sane_band():
    with pytest.raises(HTTPException) as exc:
        await set_fx_settings(
            FxSettingsUpdate(uah_per_usd_override=Decimal("5000")), _make_user(), _db({})
        )

    assert exc.value.status_code == 400
    assert "between" in exc.value.detail


@pytest.mark.asyncio
async def test_put_rejects_a_non_nbu_source_url():
    """The URL is fetched server-side, so the allowlist is an SSRF guard."""
    with pytest.raises(HTTPException) as exc:
        await set_fx_settings(
            FxSettingsUpdate(source_url="https://evil.example.com/rates.json"),
            _make_user(),
            _db({}),
        )

    assert exc.value.status_code == 400
    assert "bank.gov.ua" in exc.value.detail


@pytest.mark.asyncio
async def test_put_accepts_an_nbu_source_url():
    db = _db({}, row=None)
    url = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&json"

    await set_fx_settings(FxSettingsUpdate(source_url=url), _make_user(), db)

    written = [c[0][0] for c in db.add.call_args_list if isinstance(c[0][0], AppSetting)]
    assert written[0].key == FX_SOURCE_URL
    assert written[0].value == url


@pytest.mark.asyncio
async def test_put_with_an_empty_body_is_a_400():
    with pytest.raises(HTTPException) as exc:
        await set_fx_settings(FxSettingsUpdate(), _make_user(), _db({}))

    assert exc.value.status_code == 400


# ─── Clear (revoke symmetry) ─────────────────────────────────


@pytest.mark.asyncio
async def test_delete_clears_the_override_and_reverts_to_auto():
    existing = AppSetting(key=FX_UAH_PER_USD_OVERRIDE, value="41.5")
    db = _db({FX_UAH_PER_USD_CACHED: "44.6395"}, row=existing)

    await clear_fx_override(_make_user(), db)

    db.delete.assert_awaited_once_with(existing)
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_every_fx_change_is_audited():
    """The sprint is forward-only, so this trail is the only way to answer 'which
    orders were booked at the bad rate' after the fact."""
    db = _db({}, row=None)
    owner = _make_user()

    await set_fx_settings(
        FxSettingsUpdate(uah_per_usd_override=Decimal("41.5")), owner, db
    )

    audits = [
        c[0][0]
        for c in db.add.call_args_list
        if type(c[0][0]).__name__ == "FxRateAudit"
    ]
    assert len(audits) == 1
    assert audits[0].actor_id == owner.id
    assert audits[0].new_value == "41.5"
    assert audits[0].source == "manual"


# ─── Guard ───────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.DESIGNER])
async def test_non_owner_roles_are_rejected(role):
    """All three FX endpoints depend on require_role(OWNER) — exercise the
    dependency itself, since calling the coroutines directly bypasses Depends."""
    checker = require_role(UserRole.OWNER)

    with pytest.raises(HTTPException) as exc:
        await checker(current_user=_make_user(role=role))

    assert exc.value.status_code == 403
