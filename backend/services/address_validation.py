"""
OrderHub CRM — Address Validation Service (ADDR-VAL-1)

Validates a non-UA shipping address against the Google Address Validation API and
returns an advisory AddressVerdict. Provider-agnostic at the seam: `validate_address`
owns the coverage gate + key loading, and delegates the actual call to an
AddressValidationProvider, so a second provider can be slotted in per country later.

Two invariants:
  • UA addresses are NEVER sent to Google — they belong to the Nova Poshta flow.
  • Nothing here is fatal. Missing key, timeout, HTTP error and decrypt failure all
    resolve to the UNAVAILABLE verdict, mirroring the idlaser "a missing optional
    dependency is non-fatal" convention (CLAUDE.md).
"""

import logging
from datetime import datetime, timezone
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.app_setting import GOOGLE_ADDRESS_VALIDATION_API_KEY, AppSetting
from models.order import AddressValidationStatus
from schemas.address_validation import (
    AddressComponents,
    AddressFieldDiff,
    AddressInput,
    AddressVerdict,
)
from services.encryption_service import decrypt_value

logger = logging.getLogger(__name__)

GOOGLE_ENDPOINT = "https://addressvalidation.googleapis.com/v1:validateAddress"

# Manager-facing click, not a background sync: fail fast rather than hang. This is
# deliberately shorter than the 30s used by nova_poshta/shopify_sync, and there is
# no tenacity retry — an advisory check is not worth a 90s worst case.
TIMEOUT_SECONDS = 10.0

# Google Address Validation coverage, snapshot 2026-07-17. Source:
# https://developers.google.com/maps/documentation/address-validation/coverage
# The page lists 40 regions, of which IN and JP are marked preview (pre-GA).
GA_COUNTRIES = frozenset({
    "AR", "AT", "AU", "BE", "BG", "BR", "CA", "CH", "CL", "CO",
    "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GB", "HR", "HU",
    "IE", "IT", "LT", "LU", "LV", "MX", "MY", "NL", "NO", "NZ",
    "PL", "PR", "PT", "SE", "SG", "SI", "SK", "US",
})

# Preview regions we still send. Empty for now: JP was deferred (AV1-FIX-2) after the
# real-API sign-off showed romaji input comes back as fullwidth kanji — a
# script-conversion "diff" on ~100% of JP orders, plus 2/6 valid addresses returning
# couldnt_verify. So JP short-circuits to UNSUPPORTED with no Google call, like IN.
# TODO: re-add "JP" here once the diff layer suppresses script-conversion-only changes
# (romaji-in → kanji-out); until then JP preview quality is not shippable.
PREVIEW_COUNTRIES_SENT = frozenset()

SUPPORTED_COUNTRIES = GA_COUNTRIES | PREVIEW_COUNTRIES_SENT

# Google's validationGranularity values that mean "we pinned an actual building".
_PRECISE_GRANULARITY = frozenset({"PREMISE", "SUB_PREMISE"})
# ...and the ones that mean Google could not resolve the address at all.
_UNRESOLVED_GRANULARITY = frozenset({"OTHER", "GRANULARITY_UNSPECIFIED", ""})


class AddressValidationProvider(Protocol):
    """The seam a second provider would implement (ADDR-VAL-1 rule 1)."""

    async def validate(self, address: AddressInput) -> AddressVerdict: ...


def _verdict(status: AddressValidationStatus, message: str) -> AddressVerdict:
    return AddressVerdict(
        status=status,
        message=message,
        validated_at=datetime.now(timezone.utc),
    )


async def load_google_api_key(db: AsyncSession) -> str | None:
    """Load + decrypt the global Google API key, or None if unset/undecryptable.

    decrypt_value() has no internal error handling — an InvalidToken (e.g. after an
    ENCRYPTION_KEY rotation) would propagate — so it is guarded here and reported as
    "no usable key", which the caller turns into the non-fatal UNAVAILABLE verdict.
    """
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == GOOGLE_ADDRESS_VALIDATION_API_KEY)
    )
    setting = result.scalar_one_or_none()
    if setting is None or not setting.value_encrypted:
        return None
    try:
        return decrypt_value(setting.value_encrypted)
    except Exception:
        logger.exception(
            "[ADDR-VAL] Stored Google API key could not be decrypted — "
            "re-enter it in Settings (has ENCRYPTION_KEY changed?)"
        )
        return None


async def validate_address(db: AsyncSession, address: AddressInput) -> AddressVerdict:
    """Validate a shipping address, applying the coverage gate before any API call."""
    country = (address.country or "").strip().upper()

    if not country:
        return _verdict(
            AddressValidationStatus.COULDNT_VERIFY,
            "This order has no shipping country set.",
        )

    # UA is checked BEFORE the allowlist on purpose: UA is not in Google's coverage
    # list at all, so an allowlist-first gate would report "unsupported" when the real
    # meaning is "this ships via Nova Poshta".
    if country == "UA":
        return _verdict(
            AddressValidationStatus.UA,
            "Ukrainian addresses are handled by Nova Poshta, not Google.",
        )

    if country not in SUPPORTED_COUNTRIES:
        return _verdict(
            AddressValidationStatus.UNSUPPORTED,
            f"Google Address Validation does not cover {country}.",
        )

    if not address.has_address():
        return _verdict(
            AddressValidationStatus.COULDNT_VERIFY,
            "This order has no street, city or postal code to check.",
        )

    api_key = await load_google_api_key(db)
    if api_key is None:
        return _verdict(
            AddressValidationStatus.UNAVAILABLE,
            "No Google API key configured — add one in Settings › Address Validation.",
        )

    provider = GoogleAddressValidationProvider(api_key)
    try:
        return await provider.validate(address)
    except httpx.HTTPStatusError as exc:
        # Log Google's own error status/message, never the request URL, params or
        # headers — those carry the API key. Google's error body is
        # {"error": {code, message, status}} and does not echo the key back.
        logger.error(
            "[ADDR-VAL] Google Address Validation rejected the request: HTTP %s — %s",
            exc.response.status_code,
            exc.response.text,
        )
        # A 400 (INVALID_ARGUMENT) means Google rejected the *address* — too sparse or
        # malformed to parse — not that the service is down. Report that honestly as
        # "couldn't verify" instead of the misleading "try again shortly" outage copy.
        if exc.response.status_code == 400:
            return _verdict(
                AddressValidationStatus.COULDNT_VERIFY,
                "Google could not check this address — it may be incomplete or malformed.",
            )
        return _verdict(
            AddressValidationStatus.UNAVAILABLE,
            "Address validation is temporarily unavailable. Try again shortly.",
        )
    except Exception:
        # Non-fatal by design: an advisory check must never 500 an order view.
        logger.exception("[ADDR-VAL] Google Address Validation call failed")
        return _verdict(
            AddressValidationStatus.UNAVAILABLE,
            "Address validation is temporarily unavailable. Try again shortly.",
        )


class GoogleAddressValidationProvider:
    """Google Address Validation API implementation of AddressValidationProvider."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def validate(self, address: AddressInput) -> AddressVerdict:
        payload = _build_google_payload(address)
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            # Header auth, not ?key=: httpx puts the request URL into HTTPStatusError,
            # so a key in the query string ends up in any traceback we log.
            response = await client.post(
                GOOGLE_ENDPOINT,
                headers={"X-Goog-Api-Key": self._api_key},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        result = (body or {}).get("result") or {}
        verdict = result.get("verdict") or {}
        if not verdict:
            return _verdict(
                AddressValidationStatus.COULDNT_VERIFY,
                "Google returned no verdict for this address.",
            )

        google_address = result.get("address") or {}
        components = _extract_components(google_address)
        diff = _build_diff(address, components)
        status = _map_status(verdict)

        return AddressVerdict(
            status=status,
            message=_message_for(status, diff),
            formatted_address=google_address.get("formattedAddress"),
            components=components,
            diff=diff,
            validated_at=datetime.now(timezone.utc),
        )


def _build_google_payload(address: AddressInput) -> dict:
    """Assemble the Google request. regionCode is always sent — Google explicitly
    recommends it for the preview regions (JP) to improve results."""
    address_lines = [
        line.strip()
        for line in (address.street_1, address.street_2)
        if line and line.strip()
    ]
    postal_address: dict = {
        "regionCode": (address.country or "").strip().upper(),
        "addressLines": address_lines,
    }
    if address.city and address.city.strip():
        postal_address["locality"] = address.city.strip()
    if address.state and address.state.strip():
        postal_address["administrativeArea"] = address.state.strip()
    if address.zip and address.zip.strip():
        postal_address["postalCode"] = address.zip.strip()
    return {"address": postal_address}


def _extract_components(google_address: dict) -> AddressComponents:
    postal = google_address.get("postalAddress") or {}
    lines = postal.get("addressLines") or []
    return AddressComponents(
        street_1=lines[0] if len(lines) > 0 else None,
        street_2=lines[1] if len(lines) > 1 else None,
        city=postal.get("locality"),
        state=postal.get("administrativeArea"),
        zip=postal.get("postalCode"),
        country=postal.get("regionCode"),
    )


def _map_status(verdict: dict) -> AddressValidationStatus:
    """Map Google's verdict flags onto our six-value badge status (OQ-6).

    hasInferredComponents is deliberately NOT a needs_attention trigger (AV1-FIX-1).
    The sign-off showed Google sets it for benign completions — a +4 zip, an "Avenue"
    → "Ave" suffix — which flagged ~every US address (the White House included) for
    nothing actionable. Inference Google is unsure about additionally sets
    hasUnconfirmedComponents, so needs_attention is driven by unconfirmed/replaced
    components (plus the granularity gate); an inference-only delta stays verified.
    The diff is still returned either way, so the manager sees the change regardless.
    """
    granularity = verdict.get("validationGranularity") or ""
    if granularity in _UNRESOLVED_GRANULARITY:
        return AddressValidationStatus.COULDNT_VERIFY

    if (
        verdict.get("addressComplete")
        and not verdict.get("hasUnconfirmedComponents")
        and not verdict.get("hasReplacedComponents")
        and granularity in _PRECISE_GRANULARITY
    ):
        return AddressValidationStatus.VERIFIED

    return AddressValidationStatus.NEEDS_ATTENTION


def _norm(value: str | None) -> str:
    return (value or "").strip().casefold()


def _build_diff(original: AddressInput, suggested: AddressComponents) -> list[AddressFieldDiff]:
    """Report fields where Google's standardised value differs from ours.

    Compared case/whitespace-insensitively but reported verbatim, so the UI can show
    the real "London → Romford" rather than a normalised artefact. Fields Google did
    not return are skipped — an absent value is not a suggested deletion.
    """
    diff: list[AddressFieldDiff] = []
    for field in ("street_1", "street_2", "city", "state", "zip", "country"):
        original_value = getattr(original, field)
        suggested_value = getattr(suggested, field)
        if not suggested_value:
            continue
        if _norm(original_value) != _norm(suggested_value):
            diff.append(
                AddressFieldDiff(
                    field=field, original=original_value, suggested=suggested_value
                )
            )
    return diff


def _message_for(status: AddressValidationStatus, diff: list[AddressFieldDiff]) -> str:
    if status is AddressValidationStatus.VERIFIED:
        return "Google confirmed this address."
    if status is AddressValidationStatus.NEEDS_ATTENTION:
        if diff:
            fields = ", ".join(d.field for d in diff)
            return f"Google suggests changes to: {fields}."
        return "Google could not fully confirm this address."
    return "Google could not resolve this address."
