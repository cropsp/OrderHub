"""
OrderHub CRM — App Settings Router (ADDR-VAL-1, WB-1, FX-CONVERSION)

Owner-only management of global, app-level configuration: the Google Address
Validation key, the WesternBid credential pair, and the UAH/USD FX rate.

Two storage disciplines live side by side (models/app_setting.py):
  * SECRETS (Google key, WB pair) — Fernet-encrypted at rest, exposed only as a
    masked `is_set` + `last4`; the plaintext is write-only.
  * NON-SECRET config (FX) — stored in the clear and returned as-is. An exchange
    rate is public, and encrypting it would make COGS booking silently fail on an
    ENCRYPTION_KEY rotation.

Guard: every route here is `require_role(UserRole.OWNER)`. The FX rate re-prices
every subsequent shipment globally, so it is owner business config — but note the
deliberate read/write asymmetry: the rate PROVENANCE (which rate was applied, and
when) travels with the cost on the order + BOM surfaces under VIEW_COSTS, so a
manager who can see a converted COGS can also explain it without reaching here.
"""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.app_setting import (
    FX_SOURCE_URL,
    FX_UAH_PER_USD_CACHED,
    FX_UAH_PER_USD_OVERRIDE,
    GOOGLE_ADDRESS_VALIDATION_API_KEY,
    WESTERNBID_API_KEY,
    WESTERNBID_LOGIN,
    AppSetting,
)
from models.user import User, UserRole
from routers.dependencies import require_role
from schemas.app_setting import (
    ApiKeyStatusResponse,
    ApiKeyUpdate,
    WesternBidCredentialsStatus,
    WesternBidCredentialsUpdate,
)
from schemas.fx import FxSettingsResponse, FxSettingsUpdate
from services import fx_service
from services.encryption_service import encrypt_value
from logger import get_logger

logger = get_logger("routers.app_settings")


router = APIRouter(prefix="/api/settings", tags=["settings"])


def _status(setting: AppSetting | None) -> ApiKeyStatusResponse:
    if setting is None or not setting.value_encrypted:
        return ApiKeyStatusResponse(is_set=False)
    return ApiKeyStatusResponse(
        is_set=True, last4=setting.last4, updated_at=setting.updated_at
    )


async def _get_setting(db: AsyncSession, key: str) -> AppSetting | None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    return result.scalar_one_or_none()


@router.get("/address-validation", response_model=ApiKeyStatusResponse)
async def get_address_validation_key_status(
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """Masked status of the Google Address Validation API key (owner only).

    Never decrypts: `last4` was captured at write time precisely so this path does
    not have to materialise the plaintext key.
    """
    return _status(await _get_setting(db, GOOGLE_ADDRESS_VALIDATION_API_KEY))


@router.put("/address-validation", response_model=ApiKeyStatusResponse)
async def set_address_validation_key(
    body: ApiKeyUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """Set or replace the Google Address Validation API key (owner only).

    Write-only: the response is the masked status, never the key.
    """
    api_key = body.api_key.strip()
    setting = await _get_setting(db, GOOGLE_ADDRESS_VALIDATION_API_KEY)

    if setting is None:
        setting = AppSetting(key=GOOGLE_ADDRESS_VALIDATION_API_KEY)
        db.add(setting)

    setting.value_encrypted = encrypt_value(api_key)
    setting.last4 = api_key[-4:]
    setting.updated_by_id = current_user.id

    await db.flush()
    await db.commit()
    await db.refresh(setting)

    logger.info(f"Google Address Validation API key updated by {current_user.email}")
    return _status(setting)


def _wb_status(
    api_setting: AppSetting | None, login_setting: AppSetting | None
) -> WesternBidCredentialsStatus:
    api_set = bool(api_setting and api_setting.value_encrypted)
    login_set = bool(login_setting and login_setting.value_encrypted)
    updated_candidates = [
        s.updated_at for s in (api_setting, login_setting) if s is not None
    ]
    return WesternBidCredentialsStatus(
        api_key_is_set=api_set,
        api_key_last4=api_setting.last4 if api_set else None,
        login_is_set=login_set,
        login_last4=login_setting.last4 if login_set else None,
        updated_at=max(updated_candidates) if updated_candidates else None,
    )


async def _upsert_setting(
    db: AsyncSession, key: str, plaintext: str, current_user: User
) -> AppSetting:
    setting = await _get_setting(db, key)
    if setting is None:
        setting = AppSetting(key=key)
        db.add(setting)
    setting.value_encrypted = encrypt_value(plaintext)
    setting.last4 = plaintext[-4:]
    setting.updated_by_id = current_user.id
    return setting


@router.get("/westernbid", response_model=WesternBidCredentialsStatus)
async def get_westernbid_credentials_status(
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """Masked status of the WesternBid credential pair (owner only).

    Both the API key and the login are secrets (WB-1 rule 5); this never decrypts
    either — it reports presence + the trailing 4 chars captured at write time.
    """
    return _wb_status(
        await _get_setting(db, WESTERNBID_API_KEY),
        await _get_setting(db, WESTERNBID_LOGIN),
    )


@router.put("/westernbid", response_model=WesternBidCredentialsStatus)
async def set_westernbid_credentials(
    body: WesternBidCredentialsUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """Set or replace the WesternBid credential pair (owner only). Write-only:
    the response is the masked status, never the plaintext."""
    api_key = body.api_key.strip()
    login = body.login.strip()

    api_setting = await _upsert_setting(db, WESTERNBID_API_KEY, api_key, current_user)
    login_setting = await _upsert_setting(db, WESTERNBID_LOGIN, login, current_user)

    await db.flush()
    await db.commit()
    await db.refresh(api_setting)
    await db.refresh(login_setting)

    logger.info(f"WesternBid credentials updated by {current_user.email}")
    return _wb_status(api_setting, login_setting)


# ── FX rate (FX-CONVERSION) ────────────────────────────────────────────────


async def _fx_response(db: AsyncSession) -> FxSettingsResponse:
    """Effective state + both raw inputs, so the UI can show what clearing the
    override would revert to BEFORE the owner clears it."""
    settings = await fx_service.load_fx_settings(db)
    resolved = await fx_service.resolve(db)
    return FxSettingsResponse(
        uah_per_usd_effective=resolved.uah_per_usd,
        source=resolved.source,
        uah_per_usd_override=_as_decimal(settings.get(FX_UAH_PER_USD_OVERRIDE)),
        uah_per_usd_cached=_as_decimal(settings.get(FX_UAH_PER_USD_CACHED)),
        rate_date=resolved.rate_date,
        fetched_at=resolved.fetched_at,
        is_stale=resolved.is_stale(),
        source_url=fx_service.get_source_url(settings),
    )


def _as_decimal(raw: str | None):
    """Render a stored value for display. A corrupted row shows as unset here and
    is logged loudly by fx_service.resolve — it must not 500 the settings page."""
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        logger.error("[FX] Unparseable stored value %r", raw)
        return None


@router.get("/fx", response_model=FxSettingsResponse)
async def get_fx_settings(
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """Current UAH/USD rate configuration (owner only).

    `uah_per_usd_*` is NBU's quote direction — UAH per 1 USD — so converting a UAH
    cost to USD divides by it. See services/fx_service.py.
    """
    return await _fx_response(db)


@router.put("/fx", response_model=FxSettingsResponse)
async def set_fx_settings(
    body: FxSettingsUpdate,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """Set the FX source URL and/or the manual override (owner only).

    Clearing the override is DELETE /fx/override, not an empty value here — see
    that endpoint. Every change is recorded in fx_rate_audit.
    """
    if body.source_url is None and body.uah_per_usd_override is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide source_url and/or uah_per_usd_override",
        )

    if body.source_url is not None:
        try:
            url = fx_service.validate_source_url(body.source_url)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        await fx_service.set_plain_setting(
            db, FX_SOURCE_URL, url, actor_id=current_user.id, source="manual"
        )

    if body.uah_per_usd_override is not None:
        rate = body.uah_per_usd_override
        if not (
            fx_service.FX_MIN_UAH_PER_USD <= rate <= fx_service.FX_MAX_UAH_PER_USD
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Rate must be between {fx_service.FX_MIN_UAH_PER_USD} and "
                    f"{fx_service.FX_MAX_UAH_PER_USD} UAH per 1 USD"
                ),
            )
        await fx_service.set_plain_setting(
            db,
            FX_UAH_PER_USD_OVERRIDE,
            str(rate),
            actor_id=current_user.id,
            source="manual",
        )

    await db.commit()
    logger.info(f"FX settings updated by {current_user.email}")
    return await _fx_response(db)


@router.delete("/fx/override", response_model=FxSettingsResponse)
async def clear_fx_override(
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: AsyncSession = Depends(get_db),
):
    """Clear the manual override, reverting to the auto-fetched NBU rate.

    A distinct endpoint rather than a null in PUT: the DB CHECK forbids a row with
    neither value column set, so clearing DELETEs the row — and "revert to auto"
    silently changes the rate used by every future shipment, which deserves its own
    audited operation rather than an empty-string special case.
    """
    await fx_service.clear_plain_setting(
        db, FX_UAH_PER_USD_OVERRIDE, actor_id=current_user.id, source="clear"
    )
    await db.commit()
    logger.info(f"FX manual override cleared by {current_user.email}")
    return await _fx_response(db)
