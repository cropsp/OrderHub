"""
OrderHub CRM — Application Configuration

Loads settings from environment variables using Pydantic Settings.
"""

from functools import lru_cache
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file or environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ─── Database ──────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://crm:crm_pass@postgres:5432/crm_db"
    POSTGRES_USER: str = "crm"
    POSTGRES_PASSWORD: str = "crm_pass"
    POSTGRES_DB: str = "crm_db"

    # ─── Security ──────────────────────────────────────────────
    SECRET_KEY: str = "change-me-generate-a-real-secret-key-min-32"
    ENCRYPTION_KEY: str = Field(
        "change-me-generate-a-real-fernet-key",
        validation_alias=AliasChoices('ENCRYPTION_KEY', 'FERNET_KEY')
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ─── Email (SMTP) ─────────────────────────────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_NAME: str = "OrderHub"

    # ─── App ───────────────────────────────────────────────────
    BASE_CURRENCY: str = "USD"
    FRONTEND_URL: str = "http://localhost:3000"
    UPLOADS_DIR: str = "/app/uploads"
    ENVIRONMENT: str = "development"

    # ─── MCP ───────────────────────────────────────────────────
    MCP_SERVER_PORT: int = 3001

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — created once per process."""
    return Settings()
