"""ADDR-VAL-1 — Router tests for the global app-settings API key endpoints.

Calls the endpoint coroutines directly (mirroring test_shipping_router.py). Uses the
real encryption_service so the encrypt/decrypt round-trip is genuinely exercised
rather than mocked away.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from models.app_setting import GOOGLE_ADDRESS_VALIDATION_API_KEY, AppSetting
from models.user import UserRole
from routers.app_settings import (
    get_address_validation_key_status,
    set_address_validation_key,
)
from routers.dependencies import require_role
from schemas.app_setting import ApiKeyUpdate
from services.encryption_service import decrypt_value

PLAINTEXT_KEY = "AIzaSyExampleGoogleApiKey_00001234"


@pytest.fixture(autouse=True)
def _real_fernet_key(monkeypatch):
    """Point encryption_service at a valid throwaway Fernet key.

    backend/config.py defaults ENCRYPTION_KEY to a 'change-me' placeholder that is
    not a valid Fernet key, so without this the round-trip test would blow up in
    Fernet() rather than in the code under test.
    """
    settings = MagicMock()
    settings.ENCRYPTION_KEY = Fernet.generate_key().decode()
    monkeypatch.setattr("services.encryption_service.get_settings", lambda: settings)


def _make_user(role=UserRole.OWNER):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.email = "owner@example.com"
    return user


def _db_returning(setting):
    result = MagicMock()
    result.scalar_one_or_none.return_value = setting
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    return db


# ─── Masked read ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_is_not_set_when_no_row_exists():
    result = await get_address_validation_key_status(_make_user(), _db_returning(None))

    assert result.is_set is False
    assert result.last4 is None


@pytest.mark.asyncio
async def test_status_reports_last4_from_the_stored_column():
    setting = AppSetting(
        key=GOOGLE_ADDRESS_VALIDATION_API_KEY,
        value_encrypted="cipher",  # deliberately not decryptable
        last4="1234",
    )

    result = await get_address_validation_key_status(_make_user(), _db_returning(setting))

    # value_encrypted is junk, so reaching last4 at all proves no decrypt happened.
    assert result.is_set is True
    assert result.last4 == "1234"


def test_read_path_does_not_import_decrypt_value():
    """OQ-5 guard: the masked read must never materialise the plaintext key."""
    import routers.app_settings as module

    assert not hasattr(module, "decrypt_value"), (
        "routers/app_settings.py must not import decrypt_value — last4 is stored at "
        "write time precisely so the GET path never decrypts."
    )


@pytest.mark.asyncio
async def test_status_response_never_contains_the_plaintext_key():
    """The masked schema must have no field capable of leaking the secret."""
    setting = AppSetting(
        key=GOOGLE_ADDRESS_VALIDATION_API_KEY,
        value_encrypted="cipher-blob-that-is-not-the-key",
        last4="1234",
    )

    result = await get_address_validation_key_status(_make_user(), _db_returning(setting))
    body = result.model_dump_json()

    assert PLAINTEXT_KEY not in body
    assert "cipher-blob-that-is-not-the-key" not in body
    assert "value_encrypted" not in body


# ─── Write ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_setting_a_new_key_encrypts_and_stores_last4():
    db = _db_returning(None)

    result = await set_address_validation_key(
        ApiKeyUpdate(api_key=PLAINTEXT_KEY), _make_user(), db
    )

    db.add.assert_called_once()
    stored = db.add.call_args.args[0]
    assert stored.value_encrypted != PLAINTEXT_KEY, "key must not be stored in plaintext"
    assert decrypt_value(stored.value_encrypted) == PLAINTEXT_KEY
    assert stored.last4 == "1234"
    assert result.is_set is True
    assert result.last4 == "1234"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_replacing_an_existing_key_updates_in_place():
    existing = AppSetting(
        key=GOOGLE_ADDRESS_VALIDATION_API_KEY,
        value_encrypted="old-cipher",
        last4="9999",
    )
    db = _db_returning(existing)

    await set_address_validation_key(
        ApiKeyUpdate(api_key=PLAINTEXT_KEY), _make_user(), db
    )

    db.add.assert_not_called(), "existing row is mutated, not re-added"
    assert decrypt_value(existing.value_encrypted) == PLAINTEXT_KEY
    assert existing.last4 == "1234"


@pytest.mark.asyncio
async def test_key_is_trimmed_before_encryption():
    """A pasted key often carries whitespace; it must not become part of the secret."""
    db = _db_returning(None)

    await set_address_validation_key(
        ApiKeyUpdate(api_key=f"  {PLAINTEXT_KEY}\n"), _make_user(), db
    )

    stored = db.add.call_args.args[0]
    assert decrypt_value(stored.value_encrypted) == PLAINTEXT_KEY
    assert stored.last4 == "1234"


@pytest.mark.asyncio
async def test_write_records_who_changed_it():
    db = _db_returning(None)
    owner = _make_user()

    await set_address_validation_key(ApiKeyUpdate(api_key=PLAINTEXT_KEY), owner, db)

    assert db.add.call_args.args[0].updated_by_id == owner.id


def test_empty_key_is_rejected_by_the_schema():
    with pytest.raises(ValueError):
        ApiKeyUpdate(api_key="")


# ─── Role gating ─────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.DESIGNER])
async def test_non_owner_roles_are_rejected(role):
    """Both endpoints depend on require_role(OWNER) — exercise the dependency itself,
    since calling the coroutine directly bypasses FastAPI's dependency injection."""
    from fastapi import HTTPException

    checker = require_role(UserRole.OWNER)
    with pytest.raises(HTTPException) as exc:
        await checker(current_user=_make_user(role=role))

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_owner_passes_the_role_gate():
    checker = require_role(UserRole.OWNER)
    owner = _make_user(role=UserRole.OWNER)

    assert await checker(current_user=owner) is owner
