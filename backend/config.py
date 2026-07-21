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
    # Optional independent refresh-token signing key. If unset, auth_service
    # falls back to deriving from SECRET_KEY (preserves existing tokens on
    # rollout). See SEC-01 in audit_artifacts/SECURITY_REPORT.md.
    REFRESH_SECRET_KEY: str | None = None
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

    # ─── WesternBid (WB-1) ─────────────────────────────────────
    # Base URL is configurable, defaulting to the sandbox (task rule 7). Switch
    # to production `https://system.westernbid.com` via the env var once the
    # production key (ticket #1048) arrives. The client appends `/api/v1/`.
    WESTERNBID_BASE_URL: str = "https://wbdeveloper.systems"

    # ─── ID-Laser draft pipeline ───────────────────────────────
    # Paths default to the git submodule layout (S005):
    # backend/external/idlaser is COPYed into the image at
    # /app/external/idlaser by the Dockerfile and editable-installed there.
    IDLASER_TEMPLATE_PATH: str = "/app/external/idlaser/7001.svg"
    IDLASER_MODEL_PATH: str = "/app/external/idlaser/models/card_detector.onnx"
    IDLASER_TIMEOUT_S: int = 60

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    def _validate_production_secrets(self) -> None:
        """Fail-fast if production is using placeholder secrets (SEC-03 guard)."""
        if self.ENVIRONMENT != "production":
            return
        if self.SECRET_KEY.startswith("change-me"):
            raise RuntimeError(
                "ENVIRONMENT=production but SECRET_KEY is the default placeholder. "
                "Set SECRET_KEY to a real value (e.g. `python -c 'import secrets; "
                "print(secrets.token_urlsafe(32))'`) before starting the app."
            )
        if self.ENCRYPTION_KEY.startswith("change-me"):
            raise RuntimeError(
                "ENVIRONMENT=production but ENCRYPTION_KEY is the default placeholder. "
                "Set ENCRYPTION_KEY to a real Fernet key (e.g. `python -c 'from "
                "cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`) "
                "before starting the app."
            )


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — created once per process."""
    settings = Settings()
    settings._validate_production_secrets()
    return settings
