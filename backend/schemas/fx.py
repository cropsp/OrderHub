"""
OrderHub CRM — FX Settings Schemas (FX-CONVERSION)

Read + write models for the global UAH/USD rate configuration.

Every numeric field here is named `uah_per_usd_*` on purpose. NBU publishes UAH
per 1 USD, so a UAH→USD conversion is a division; a field called `rate` or
`amount` would (a) invite the inversion bug and (b) silently inherit an existing
classification in tests/test_money_field_completeness.py, whose field map is keyed
by BARE FIELD NAME globally. These are rates, not amounts — classified `neutral`.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class FxSettingsResponse(BaseModel):
    """Effective FX state plus the provenance needed to explain it.

    `uah_per_usd_effective` is what conversions will actually use: the override if
    one is set, else the cached NBU rate, else None (nothing converts).
    """

    model_config = ConfigDict(from_attributes=True)

    uah_per_usd_effective: Decimal | None = None
    source: str | None = None  # "manual" | "nbu" | None
    uah_per_usd_override: Decimal | None = None
    uah_per_usd_cached: Decimal | None = None
    # NBU's own exchangedate for the cached rate — the banking day it is FOR, which
    # is one day ahead of the fetch (NBU publishes the next banking day's rate).
    rate_date: date | None = None
    fetched_at: datetime | None = None
    is_stale: bool = False
    source_url: str = ""


class FxSettingsUpdate(BaseModel):
    """Write payload. Both fields optional; at least one must be present.

    Clearing the override is NOT done here — it is DELETE /api/settings/fx/override,
    so that "revert to auto" is an explicit, separately audited operation rather
    than an empty-string special case.
    """

    source_url: str | None = Field(default=None, max_length=500)
    uah_per_usd_override: Decimal | None = Field(default=None, gt=0)
