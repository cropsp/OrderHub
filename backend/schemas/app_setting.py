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


class WesternBidCredentialsStatus(BaseModel):
    """Masked status of the WesternBid credential pair (WB-1).

    Both the API key and the login are secrets (task rule 5), so neither
    plaintext is ever returned — only presence + trailing 4 chars, exactly like
    ApiKeyStatusResponse but for the pair.
    """

    model_config = ConfigDict(from_attributes=True)

    api_key_is_set: bool = False
    api_key_last4: str | None = None
    login_is_set: bool = False
    login_last4: str | None = None
    updated_at: datetime | None = None


class WesternBidCredentialsUpdate(BaseModel):
    """Write-only payload for setting/replacing the WesternBid credential pair."""

    api_key: str = Field(..., min_length=1, max_length=500)
    login: str = Field(..., min_length=1, max_length=255)
