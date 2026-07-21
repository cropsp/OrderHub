"""
OrderHub CRM — App Settings Router (ADDR-VAL-1)

Owner-only management of global, app-level API keys. Currently just the Google
Address Validation key, which is Fernet-encrypted at rest and only ever exposed as
a masked `is_set` + `last4` status — the plaintext is write-only.

Mirrors the Nova Poshta key handling on the shops router (encrypt on write, never
return the secret), but app-scoped rather than shop-scoped.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.app_setting import (
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
