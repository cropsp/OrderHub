"""ADDR-VAL-1 — Service-level tests for the address validation service.

Mocks httpx.AsyncClient at the module boundary so no real HTTP fires, mirroring
tests/test_nova_poshta.py. The coverage-gate tests assert the client is never even
constructed — a UA address reaching Google would be a correctness bug, not just a
wasted call.
"""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from models.order import AddressValidationStatus
from schemas.address_validation import AddressInput
from services.address_validation import (
    GA_COUNTRIES,
    GOOGLE_ENDPOINT,
    SUPPORTED_COUNTRIES,
    validate_address,
)


def _response(json_payload):
    r = MagicMock()
    r.json.return_value = json_payload
    r.raise_for_status = MagicMock()
    return r


def _async_client_cm(post_mock):
    """Build a mock context manager whose client's .post is post_mock."""
    client = MagicMock()
    client.post = post_mock
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _db_with_key(encrypted: str | None = "cipher"):
    """AsyncMock db whose app_settings lookup yields a stored key (or nothing)."""
    setting = None
    if encrypted is not None:
        setting = MagicMock()
        setting.value_encrypted = encrypted
    result = MagicMock()
    result.scalar_one_or_none.return_value = setting
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


def _uk_address(**overrides):
    defaults = dict(
        street_1="12 Example Road",
        street_2=None,
        city="London",
        state=None,
        zip="RM6 4TJ",
        country="GB",
    )
    defaults.update(overrides)
    return AddressInput(**defaults)


def _verdict_body(verdict: dict, address: dict | None = None):
    return {"result": {"verdict": verdict, "address": address or {}}}


# ─── Coverage gate — must short-circuit with NO API call ──────

@pytest.mark.asyncio
async def test_ua_short_circuits_without_calling_google():
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient") as client_cls:
        result = await validate_address(db, _uk_address(country="UA", city="Київ"))

    assert result.status is AddressValidationStatus.UA
    client_cls.assert_not_called(), "UA addresses must never reach Google"


@pytest.mark.asyncio
async def test_uncovered_country_short_circuits_without_calling_google():
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient") as client_cls:
        result = await validate_address(db, _uk_address(country="IN"))

    assert result.status is AddressValidationStatus.UNSUPPORTED
    client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_missing_country_is_couldnt_verify_without_calling_google():
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient") as client_cls:
        result = await validate_address(db, _uk_address(country=None))

    assert result.status is AddressValidationStatus.COULDNT_VERIFY
    client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_empty_address_is_couldnt_verify_without_calling_google():
    db = _db_with_key()
    empty = AddressInput(country="GB")

    with patch("services.address_validation.httpx.AsyncClient") as client_cls:
        result = await validate_address(db, empty)

    assert result.status is AddressValidationStatus.COULDNT_VERIFY
    client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_no_key_configured_is_unavailable_and_points_at_settings():
    db = _db_with_key(encrypted=None)

    with patch("services.address_validation.httpx.AsyncClient") as client_cls:
        result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.UNAVAILABLE
    assert "Settings" in (result.message or "")
    client_cls.assert_not_called()


def test_model_enum_labels_match_the_migration():
    """Regression guard: the ORM must emit the same enum labels the migration created.

    SQLAlchemy's Enum() defaults to storing member NAMES ("UA"); the migration creates
    the type with lowercase member VALUES ("ua"), so the column needs values_callable.
    Without it every write fails at runtime with
    'invalid input value for enum address_validation_status: "UA"' — which mocked-DB
    tests cannot catch. Keep this list identical to the migration's ADDRESS_VALIDATION_STATUS.
    """
    from models.order import Order

    labels = Order.__table__.c.address_validation_status.type.enums
    assert labels == [
        "verified",
        "needs_attention",
        "couldnt_verify",
        "unsupported",
        "ua",
        "unavailable",
    ]


def test_coverage_constants_match_the_documented_snapshot():
    """Guard the coverage set: 38 GA regions, no preview regions sent (AV1-FIX-2).

    JP was dropped from the send-list post-sign-off (romaji→kanji false diff), so
    SUPPORTED_COUNTRIES is now exactly the 38 GA regions.
    """
    assert len(GA_COUNTRIES) == 38
    assert len(SUPPORTED_COUNTRIES) == 38
    assert "JP" not in SUPPORTED_COUNTRIES, "JP deferred until a script-aware diff (AV1-FIX-2)"
    assert "IN" not in SUPPORTED_COUNTRIES, "IN is preview and stays off the send-list"
    assert "UA" not in SUPPORTED_COUNTRIES


# ─── Verdict mapping ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_clean_verdict_maps_to_verified():
    post = AsyncMock(return_value=_response(_verdict_body({
        "validationGranularity": "PREMISE",
        "addressComplete": True,
    })))
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.VERIFIED


@pytest.mark.asyncio
async def test_rm6_4tj_locality_correction_maps_to_needs_attention_with_diff():
    """The headline case: Google resolves the RM6 4TJ post town to Romford."""
    post = AsyncMock(return_value=_response(_verdict_body(
        verdict={
            "validationGranularity": "PREMISE",
            "addressComplete": True,
            "hasReplacedComponents": True,
        },
        address={
            "formattedAddress": "12 Example Road, Romford RM6 4TJ, UK",
            "postalAddress": {
                "regionCode": "GB",
                "postalCode": "RM6 4TJ",
                "locality": "Romford",
                "addressLines": ["12 Example Road"],
            },
        },
    )))
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.NEEDS_ATTENTION
    city_diff = [d for d in result.diff if d.field == "city"]
    assert len(city_diff) == 1
    assert city_diff[0].original == "London"
    assert city_diff[0].suggested == "Romford"
    assert result.formatted_address == "12 Example Road, Romford RM6 4TJ, UK"


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [
    "hasUnconfirmedComponents",
    "hasReplacedComponents",
])
async def test_any_google_flag_maps_to_needs_attention(flag):
    """Unconfirmed / replaced components drive needs_attention. hasInferredComponents
    deliberately does NOT (AV1-FIX-1) — see test_inferred_only_stays_verified."""
    post = AsyncMock(return_value=_response(_verdict_body({
        "validationGranularity": "PREMISE",
        "addressComplete": True,
        flag: True,
    })))
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.NEEDS_ATTENTION


@pytest.mark.asyncio
async def test_inferred_only_stays_verified():
    """AV1-FIX-1: a bare hasInferredComponents (zip+4, "Avenue"→"Ave") must NOT drag
    an otherwise-clean address out of verified. This is the White House case from the
    real-API sign-off (complete + inferred + PREMISE, nothing else)."""
    post = AsyncMock(return_value=_response(_verdict_body({
        "validationGranularity": "PREMISE",
        "addressComplete": True,
        "hasInferredComponents": True,
    })))
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.VERIFIED


@pytest.mark.asyncio
async def test_inferred_plus_unconfirmed_still_needs_attention():
    """Suppressing bare-inferred must not swallow genuine uncertainty: when Google is
    unsure about an inference it also sets hasUnconfirmedComponents, which still flags."""
    post = AsyncMock(return_value=_response(_verdict_body({
        "validationGranularity": "PREMISE",
        "addressComplete": True,
        "hasInferredComponents": True,
        "hasUnconfirmedComponents": True,
    })))
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.NEEDS_ATTENTION


@pytest.mark.asyncio
async def test_incomplete_address_maps_to_needs_attention():
    post = AsyncMock(return_value=_response(_verdict_body({
        "validationGranularity": "PREMISE",
        "addressComplete": False,
    })))
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.NEEDS_ATTENTION


@pytest.mark.asyncio
@pytest.mark.parametrize("granularity", ["OTHER", "GRANULARITY_UNSPECIFIED"])
async def test_unresolved_granularity_maps_to_couldnt_verify(granularity):
    post = AsyncMock(return_value=_response(_verdict_body({
        "validationGranularity": granularity,
        "addressComplete": True,
    })))
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.COULDNT_VERIFY


@pytest.mark.asyncio
async def test_route_granularity_maps_to_needs_attention():
    """Street-level but not a specific building — advisory, not unresolvable."""
    post = AsyncMock(return_value=_response(_verdict_body({
        "validationGranularity": "ROUTE",
        "addressComplete": True,
    })))
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.NEEDS_ATTENTION


@pytest.mark.asyncio
async def test_empty_verdict_maps_to_couldnt_verify():
    post = AsyncMock(return_value=_response({"result": {}}))
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.COULDNT_VERIFY


# ─── Graceful degradation — never fatal ──────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    httpx.TimeoutException("timed out"),
    httpx.HTTPError("boom"),
    httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock()),
    ValueError("malformed json"),
])
async def test_provider_failures_degrade_to_unavailable(failure):
    post = AsyncMock(side_effect=failure)
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.UNAVAILABLE


@pytest.mark.asyncio
async def test_undecryptable_key_degrades_to_unavailable():
    """An ENCRYPTION_KEY rotation must not 500 the endpoint — decrypt_value raises
    InvalidToken raw, so the service has to guard it."""
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient") as client_cls:
        with patch("services.address_validation.decrypt_value", side_effect=Exception("InvalidToken")):
            result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.UNAVAILABLE
    client_cls.assert_not_called()


# ─── Request shape ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_payload_carries_region_code_and_address_lines():
    post = AsyncMock(return_value=_response(_verdict_body({
        "validationGranularity": "PREMISE", "addressComplete": True,
    })))
    db = _db_with_key()
    address = _uk_address(street_2="Flat 4", state="Greater London")

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            await validate_address(db, address)

    payload = post.await_args.kwargs["json"]["address"]
    assert payload["regionCode"] == "GB"
    assert payload["addressLines"] == ["12 Example Road", "Flat 4"]
    assert payload["locality"] == "London"
    assert payload["administrativeArea"] == "Greater London"
    assert payload["postalCode"] == "RM6 4TJ"
    assert post.await_args.kwargs["headers"] == {"X-Goog-Api-Key": "plain-key"}


@pytest.mark.asyncio
async def test_api_key_is_sent_as_header_never_in_url_or_params():
    """The key must travel in X-Goog-Api-Key, never the query string.

    httpx embeds the request URL in HTTPStatusError, so a ?key= param leaks the
    secret into every logged traceback — it did exactly that during the ADDR-VAL-1
    real-API sign-off. Header auth keeps it out of URL-bearing log lines entirely.
    """
    post = AsyncMock(return_value=_response(_verdict_body({
        "validationGranularity": "PREMISE", "addressComplete": True,
    })))
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            await validate_address(db, _uk_address())

    assert post.await_args.kwargs["headers"]["X-Goog-Api-Key"] == "plain-key"
    # No params at all — and certainly no key hiding in them.
    assert "key" not in (post.await_args.kwargs.get("params") or {})
    # ...nor smuggled into the URL itself.
    assert "plain-key" not in str(post.await_args.args[0])


@pytest.mark.asyncio
async def test_http_error_logs_google_status_and_body_but_never_the_key(caplog):
    """A 403 must be diagnosable from the log without leaking the key.

    Guards the property, not the mechanism: whatever we log on the error path, the
    key must not be in it.
    """
    request = httpx.Request("POST", GOOGLE_ENDPOINT)
    response = httpx.Response(
        403,
        request=request,
        json={"error": {"code": 403, "message": "The caller does not have permission",
                        "status": "PERMISSION_DENIED"}},
    )
    post = AsyncMock(side_effect=httpx.HTTPStatusError(
        f"403 Forbidden for url '{GOOGLE_ENDPOINT}?key=plain-key'",
        request=request,
        response=response,
    ))
    db = _db_with_key()

    with caplog.at_level(logging.DEBUG):
        with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
            with patch("services.address_validation.decrypt_value", return_value="plain-key"):
                result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.UNAVAILABLE
    assert "plain-key" not in caplog.text
    # Google's own diagnosis survives, so a 403 is still actionable from the log.
    assert "403" in caplog.text
    assert "PERMISSION_DENIED" in caplog.text


@pytest.mark.asyncio
async def test_bad_address_400_is_couldnt_verify_not_unavailable():
    """A 400 INVALID_ARGUMENT means Google rejected the address (too sparse/malformed),
    not that the service is down — so it must NOT surface the misleading
    "temporarily unavailable, try again shortly" outage copy."""
    request = httpx.Request("POST", GOOGLE_ENDPOINT)
    response = httpx.Response(
        400,
        request=request,
        json={"error": {"code": 400, "message": "Invalid postal address.",
                        "status": "INVALID_ARGUMENT"}},
    )
    post = AsyncMock(side_effect=httpx.HTTPStatusError(
        "400 Bad Request", request=request, response=response,
    ))
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(db, _uk_address())

    assert result.status is AddressValidationStatus.COULDNT_VERIFY
    assert "unavailable" not in (result.message or "").lower()


@pytest.mark.asyncio
async def test_jp_short_circuits_to_unsupported():
    """AV1-FIX-2: JP was dropped from the send-list, so it now resolves to UNSUPPORTED
    with NO Google call — the httpx client must never be constructed."""
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient") as client_cls:
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(
                db, _uk_address(country="JP", city="Shibuya", zip="150-0002")
            )

    assert result.status is AddressValidationStatus.UNSUPPORTED
    client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_lowercase_country_is_normalised():
    post = AsyncMock(return_value=_response(_verdict_body({
        "validationGranularity": "PREMISE", "addressComplete": True,
    })))
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(db, _uk_address(country="gb"))

    assert result.status is AddressValidationStatus.VERIFIED
    assert post.await_args.kwargs["json"]["address"]["regionCode"] == "GB"


@pytest.mark.asyncio
async def test_diff_ignores_case_and_whitespace_noise():
    post = AsyncMock(return_value=_response(_verdict_body(
        verdict={"validationGranularity": "PREMISE", "addressComplete": True},
        address={"postalAddress": {
            "regionCode": "GB",
            "postalCode": "RM6 4TJ",
            "locality": "LONDON",
            "addressLines": ["12 Example Road"],
        }},
    )))
    db = _db_with_key()

    with patch("services.address_validation.httpx.AsyncClient", return_value=_async_client_cm(post)):
        with patch("services.address_validation.decrypt_value", return_value="plain-key"):
            result = await validate_address(db, _uk_address(city="  london "))

    assert result.diff == [], "case/whitespace-only differences are not real suggestions"
