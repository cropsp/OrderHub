"""FX-CONVERSION — storage-discipline guard for the app_settings key/value store.

`app_settings.value_encrypted` used to be NOT NULL, which was the schema-level
guarantee that everything in this table was encrypted. FX-CONVERSION made it
nullable so non-secret config (an exchange rate, a public URL) can be stored in
the clear — encrypting those would put COGS booking at the mercy of an
ENCRYPTION_KEY rotation, because decrypt_value swallows InvalidToken and returns
None (services/address_validation.py).

That trade removed the schema guarantee, so this file restores it at the test
level: every setting key must be explicitly classified as secret or plaintext, and
each write path must use the matching column.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

import models.app_setting as app_setting_module
from models.app_setting import (
    FX_UAH_PER_USD_OVERRIDE,
    GOOGLE_ADDRESS_VALIDATION_API_KEY,
    PLAINTEXT_SETTING_KEYS,
    SECRET_SETTING_KEYS,
    AppSetting,
)
from routers.app_settings import _upsert_setting
from services import fx_service


@pytest.fixture(autouse=True)
def _real_fernet_key(monkeypatch):
    settings = MagicMock()
    settings.ENCRYPTION_KEY = Fernet.generate_key().decode()
    monkeypatch.setattr("services.encryption_service.get_settings", lambda: settings)


def _known_key_constants() -> dict[str, str]:
    """Every module-level string constant in models.app_setting is a setting key."""
    return {
        name: value
        for name, value in vars(app_setting_module).items()
        if name.isupper() and isinstance(value, str) and not name.startswith("_")
    }


def test_every_setting_key_is_classified_secret_or_plaintext():
    """A new global setting must make a conscious call about how it is stored.
    Add it to SECRET_SETTING_KEYS or PLAINTEXT_SETTING_KEYS in models/app_setting.py.
    """
    classified = SECRET_SETTING_KEYS | PLAINTEXT_SETTING_KEYS
    unclassified = {
        name: value
        for name, value in _known_key_constants().items()
        if value not in classified
    }

    assert not unclassified, f"Unclassified app_settings keys: {unclassified}"


def test_no_stale_key_classifications():
    live = set(_known_key_constants().values())
    stale = (SECRET_SETTING_KEYS | PLAINTEXT_SETTING_KEYS) - live

    assert not stale, f"Classified keys that no longer exist: {stale}"


def test_secret_and_plaintext_sets_are_disjoint():
    assert not (SECRET_SETTING_KEYS & PLAINTEXT_SETTING_KEYS)


def _db_returning(row):
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    return db


@pytest.mark.asyncio
async def test_secret_write_path_populates_only_value_encrypted():
    user = MagicMock()
    user.id = uuid.uuid4()
    row = AppSetting(key=GOOGLE_ADDRESS_VALIDATION_API_KEY)
    db = _db_returning(row)

    await _upsert_setting(db, GOOGLE_ADDRESS_VALIDATION_API_KEY, "sk-secret-1234", user)

    assert row.value_encrypted
    assert row.value is None, "a secret must never land in the plaintext column"
    assert row.last4 == "1234"


@pytest.mark.asyncio
async def test_plaintext_write_path_populates_only_value():
    row = AppSetting(key=FX_UAH_PER_USD_OVERRIDE, value_encrypted="stale-cipher")
    db = _db_returning(row)

    await fx_service.set_plain_setting(
        db, FX_UAH_PER_USD_OVERRIDE, "41.5", actor_id=uuid.uuid4(), source="manual"
    )

    assert row.value == "41.5"
    assert row.value_encrypted is None
    assert row.last4 is None, "last4 is a masking aid for secrets only"


def test_check_constraint_is_declared_on_the_model():
    """The DB-level "exactly one value column" rule must exist in the model too, or
    a fresh create_all()-built test DB would not have it."""
    names = {
        c.name for c in AppSetting.__table__.constraints if c.name is not None
    }
    assert "ck_app_settings_exactly_one_value" in names
