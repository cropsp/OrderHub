"""
OrderHub CRM — Encryption Service

Provides Fernet-based symmetric encryption for API tokens (Shopify, Nova Poshta).
Tokens are encrypted before storing in DB and decrypted only at runtime.
"""

from cryptography.fernet import Fernet

from config import get_settings


def _get_fernet() -> Fernet:
    """Create a Fernet instance from the configured key."""
    settings = get_settings()
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_value(plain_text: str) -> str:
    """Encrypt a plaintext string and return base64-encoded ciphertext."""
    f = _get_fernet()
    return f.encrypt(plain_text.encode()).decode()


def decrypt_value(encrypted_text: str) -> str:
    """Decrypt a Fernet-encrypted string back to plaintext."""
    f = _get_fernet()
    return f.decrypt(encrypted_text.encode()).decode()


def mask_token(value: str | None, visible_chars: int = 4) -> str | None:
    """Return a masked version of a token for display (e.g., '****abcd')."""
    if not value:
        return None
    if len(value) <= visible_chars:
        return "*" * len(value)
    return "*" * (len(value) - visible_chars) + value[-visible_chars:]
