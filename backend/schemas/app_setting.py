"""
OrderHub CRM — App Settings Schemas (ADDR-VAL-1)

Masked read + write-only update models for global app settings. The plaintext key
is accepted on write and NEVER appears in a response model — the read side is
served entirely from `is_set` + the stored `last4`, so no decrypt happens on a GET.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyStatusResponse(BaseModel):
    """Masked status of a stored API key. Deliberately has no plaintext field."""

    model_config = ConfigDict(from_attributes=True)

    is_set: bool = False
    last4: str | None = None
    updated_at: datetime | None = None


class ApiKeyUpdate(BaseModel):
    """Write-only payload for setting/replacing an API key."""

    api_key: str = Field(..., min_length=1, max_length=500)
