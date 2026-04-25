"""
OrderHub CRM — Authentication Service

JWT token creation/verification and password hashing with bcrypt.
Access tokens: 15 min. Refresh tokens: 30 days (httpOnly cookie).
Refresh tokens use a separate signing key for cryptographic isolation.
"""

import logging
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.user import User

logger = logging.getLogger(__name__)

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"

if settings.REFRESH_SECRET_KEY:
    REFRESH_SECRET_KEY = settings.REFRESH_SECRET_KEY
else:
    REFRESH_SECRET_KEY = settings.SECRET_KEY + "-refresh"
    logger.warning(
        "REFRESH_SECRET_KEY is not set; deriving from SECRET_KEY for "
        "backward-compat. See SEC-01 — set REFRESH_SECRET_KEY in .env to "
        "an independent value (rotates all current refresh tokens)."
    )


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """Create a short-lived JWT access token (15 min)."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> str:
    """Create a long-lived JWT refresh token (30 days). Uses a separate signing key."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, REFRESH_SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str, token_type: str = "access") -> dict | None:
    """Decode and validate a JWT token. Uses the appropriate key based on token type."""
    key = REFRESH_SECRET_KEY if token_type == "refresh" else settings.SECRET_KEY
    try:
        payload = jwt.decode(token, key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> User | None:
    """Verify email + password and return the User if valid."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Fetch a user by UUID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


def generate_temp_password(length: int = 12) -> str:
    """Generate a random temporary password with guaranteed complexity."""
    special_chars = "!@#$%^&*"
    alphabet = string.ascii_letters + string.digits + special_chars

    # Guarantee at least one of each category
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(special_chars),
    ]
    # Fill remaining length with random choices from full alphabet
    password += [secrets.choice(alphabet) for _ in range(length - 4)]

    # Shuffle to avoid predictable positions
    import random
    random.SystemRandom().shuffle(password)
    return "".join(password)
