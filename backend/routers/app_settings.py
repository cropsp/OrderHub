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
from models.app_setting import GOOGLE_ADDRESS_VALIDATION_API_KEY, AppSetting
from models.user import User, UserRole
from routers.dependencies import require_role
from schemas.app_setting import ApiKeyStatusResponse, ApiKeyUpdate
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
