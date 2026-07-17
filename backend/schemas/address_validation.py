"""
OrderHub CRM — Address Validation Schemas (ADDR-VAL-1)

Provider-agnostic request/verdict models for the address-validation service.
Mirrored by hand in frontend/src/types/addressValidation.ts — keep the two in
sync (type-drift gotcha, see CLAUDE.md).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.order import AddressValidationStatus


# ─── Input ───────────────────────────────────────────────────

class AddressInput(BaseModel):
    """A shipping address to validate, assembled from an Order's shipping_* fields."""

    model_config = ConfigDict(from_attributes=True)

    street_1: str | None = None
    street_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = Field(None, max_length=2, description="ISO-2 region code")

    def has_address(self) -> bool:
        """True when there is enough here to be worth sending to a provider."""
        return any(v and v.strip() for v in (self.street_1, self.city, self.zip))


# ─── Verdict ─────────────────────────────────────────────────

class AddressComponents(BaseModel):
    """A provider's standardised rendering of the address."""

    street_1: str | None = None
    street_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None


class AddressFieldDiff(BaseModel):
    """One field where the provider's suggestion differs from what we hold."""

    field: str
    original: str | None = None
    suggested: str | None = None


class AddressVerdict(BaseModel):
    """The advisory outcome of a validation attempt.

    `status` + the time of the check are the only parts persisted on the order
    (ADDR-VAL-1 OQ-4). `formatted_address` / `components` / `diff` are returned for
    immediate display and are never written to the DB — Google's Maps Service
    Specific Terms §1.3 permit caching Address Validation content for 30 days, but
    we deliberately store nothing beyond the derived status.
    """

    model_config = ConfigDict(from_attributes=True)

    status: AddressValidationStatus
    message: str | None = None
    formatted_address: str | None = None
    components: AddressComponents | None = None
    diff: list[AddressFieldDiff] = Field(default_factory=list)
    validated_at: datetime | None = None
