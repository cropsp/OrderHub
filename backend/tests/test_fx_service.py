"""FX-CONVERSION — NBU fetch/parse, validation guards, and rate resolution.

The NBU payloads used here are verbatim from a live probe on 2026-08-02, including
its quirks: a JSON list even for one valcode, HTTP 200 + `[]` for an unknown
valcode, and an `exchangedate` that is the NEXT banking day.

Direction (UAH→USD is division) is pinned separately in test_fx_direction.py.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.app_setting import (
    FX_FETCHED_AT,
    FX_RATE_DATE,
    FX_SOURCE_URL,
    FX_UAH_PER_USD_CACHED,
    FX_UAH_PER_USD_OVERRIDE,
    AppSetting,
)
from services import fx_service
from services.fx_service import FxFetchError, FxRates


# Verbatim from the live endpoint (2026-08-02 16:04 UTC), whitespace and all.
NBU_BODY = (
    '[\n{ \n"r030":840,"txt":"Долар США","rate":44.6395,"cc":"USD",'
    '"exchangedate":"03.08.2026","special":"N"\n }\n]'
)

# What the endpoint returns when `valcode` is dropped from the URL — ~40 rows,
# alphabetically by Ukrainian name, so the Algerian dinar comes first.
NBU_ALL_CURRENCIES_BODY = (
    '[{"r030":12,"txt":"Алжирський динар","rate":0.33557,"cc":"DZD",'
    '"exchangedate":"03.08.2026","special":null},'
    '{"r030":36,"txt":"Австралійський долар","rate":31.3325,"cc":"AUD",'
    '"exchangedate":"03.08.2026","special":null},'
    '{"r030":840,"txt":"Долар США","rate":44.6395,"cc":"USD",'
    '"exchangedate":"03.08.2026","special":"N"}]'
)


# ─── Parsing ─────────────────────────────────────────────────


def test_parses_the_live_nbu_payload():
    rate, rate_date = fx_service.parse_nbu_response(NBU_BODY)

    assert rate == Decimal("44.6395")
    assert rate_date == date(2026, 8, 3)


def test_rate_keeps_full_published_precision():
    """json.loads(parse_float=Decimal) — never round-trip through a binary float."""
    rate, _ = fx_service.parse_nbu_response(NBU_BODY)

    assert str(rate) == "44.6395"
    assert rate != Decimal(44.6395)  # what float parsing would have given


def test_picks_the_usd_row_not_the_first_row():
    """The source URL is operator-editable. Dropping `valcode` returns every
    currency with DZD first, so indexing [0] would silently book Algerian dinars.
    """
    rate, _ = fx_service.parse_nbu_response(NBU_ALL_CURRENCIES_BODY)

    assert rate == Decimal("44.6395")


def test_empty_list_is_a_failure_not_a_zero_rate():
    """An unknown valcode returns HTTP 200 with `[]` — verified live. Treating that
    as a rate would divide by zero inside the ship transaction."""
    with pytest.raises(FxFetchError, match="empty list"):
        fx_service.parse_nbu_response("[]")


def test_missing_usd_row_is_a_failure():
    body = '[{"r030":12,"txt":"Алжирський динар","rate":0.33557,"cc":"DZD"}]'
    with pytest.raises(FxFetchError, match="No USD row"):
        fx_service.parse_nbu_response(body)


def test_non_json_body_is_a_failure():
    with pytest.raises(FxFetchError, match="non-JSON"):
        fx_service.parse_nbu_response("<html>502 Bad Gateway</html>")


def test_json_object_instead_of_list_is_a_failure():
    with pytest.raises(FxFetchError, match="Expected a JSON list"):
        fx_service.parse_nbu_response('{"rate": 44.6395, "cc": "USD"}')


@pytest.mark.parametrize("bad", ["0", "-44.6395", "0.0001", "5000", '"abc"', "null"])
def test_rates_outside_the_sane_band_are_rejected(bad):
    body = f'[{{"rate":{bad},"cc":"USD","exchangedate":"03.08.2026"}}]'
    with pytest.raises(FxFetchError):
        fx_service.parse_nbu_response(body)


def test_unparseable_exchangedate_is_non_fatal():
    """The rate is the payload; the date is provenance."""
    body = '[{"rate":44.6395,"cc":"USD","exchangedate":"not-a-date"}]'
    rate, rate_date = fx_service.parse_nbu_response(body)

    assert rate == Decimal("44.6395")
    assert rate_date is None


# ─── Drift guard ─────────────────────────────────────────────


def test_drift_guard_allows_a_normal_move():
    fx_service.check_drift(Decimal("45.50"), Decimal("44.6395"))  # ~1.9%


def test_drift_guard_rejects_a_misplaced_decimal_point():
    """A 10x error is 900% drift — the case this guard exists for."""
    with pytest.raises(FxFetchError, match="keeping the cached value"):
        fx_service.check_drift(Decimal("446.395"), Decimal("44.6395"))


def test_drift_guard_is_a_no_op_without_a_cached_rate():
    fx_service.check_drift(Decimal("44.6395"), None)


# ─── Source URL allowlist ────────────────────────────────────


def test_default_source_url_is_accepted():
    assert fx_service.validate_source_url(fx_service.NBU_DEFAULT_URL)


@pytest.mark.parametrize(
    "url",
    [
        "http://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json",  # not TLS
        "https://evil.example.com/rates.json",
        "https://bank.gov.ua.evil.example.com/rates.json",
        "file:///etc/passwd",
        "",
    ],
)
def test_source_url_allowlist_rejects_non_nbu_targets(url):
    """The field is owner-editable and fetched server-side, so it is an SSRF
    surface unless constrained."""
    with pytest.raises(ValueError):
        fx_service.validate_source_url(url)


def test_source_url_allows_an_nbu_subdomain():
    assert fx_service.validate_source_url("https://api.bank.gov.ua/rates?json")


# ─── Fetch ───────────────────────────────────────────────────


def _patch_httpx(monkeypatch, *, body: str = NBU_BODY, raise_for_status=None):
    response = MagicMock()
    response.text = body
    response.raise_for_status = MagicMock(
        side_effect=raise_for_status or (lambda: None)
    )

    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(
        "services.fx_service.httpx.AsyncClient", MagicMock(return_value=client)
    )
    return client


@pytest.mark.asyncio
async def test_fetch_returns_rate_and_date(monkeypatch):
    _patch_httpx(monkeypatch)

    rate, rate_date = await fx_service.fetch_nbu_rate(fx_service.NBU_DEFAULT_URL)

    assert rate == Decimal("44.6395")
    assert rate_date == date(2026, 8, 3)


@pytest.mark.asyncio
async def test_fetch_does_not_retry_a_malformed_body(monkeypatch):
    """FxFetchError is deliberately outside retry_if_exception_type: a bad body is
    just as bad three seconds later, and retrying only delays the log line."""
    client = _patch_httpx(monkeypatch, body="[]")

    with pytest.raises(FxFetchError):
        await fx_service.fetch_nbu_rate(fx_service.NBU_DEFAULT_URL)

    assert client.get.await_count == 1


# ─── Resolution ──────────────────────────────────────────────


def _db_with_settings(values: dict[str, str], *, row=None):
    """A db whose execute() serves both load_fx_settings (.all()) and
    get_setting_row (.scalar_one_or_none())."""
    result = MagicMock()
    result.all.return_value = list(values.items())
    result.scalar_one_or_none.return_value = row
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_manual_override_wins_over_the_cached_rate():
    db = _db_with_settings(
        {
            FX_UAH_PER_USD_OVERRIDE: "41.5",
            FX_UAH_PER_USD_CACHED: "44.6395",
            FX_RATE_DATE: "2026-08-03",
        }
    )

    rates = await fx_service.resolve(db)

    assert rates.uah_per_usd == Decimal("41.5")
    assert rates.source == "manual"


@pytest.mark.asyncio
async def test_falls_back_to_the_cached_rate_when_no_override():
    """This is the NBU-is-down path: nothing fetches, the cache just keeps working."""
    fetched = datetime(2026, 8, 2, 3, 30, tzinfo=timezone.utc)
    db = _db_with_settings(
        {
            FX_UAH_PER_USD_CACHED: "44.6395",
            FX_RATE_DATE: "2026-08-03",
            FX_FETCHED_AT: fetched.isoformat(),
        }
    )

    rates = await fx_service.resolve(db)

    assert rates.uah_per_usd == Decimal("44.6395")
    assert rates.source == "nbu"
    assert rates.rate_date == date(2026, 8, 3)
    assert rates.fetched_at == fetched


@pytest.mark.asyncio
async def test_no_override_and_no_cache_is_unavailable():
    rates = await fx_service.resolve(_db_with_settings({}))

    assert rates.is_usable is False
    assert rates.can_convert(frm="UAH", to="USD") is False


@pytest.mark.asyncio
async def test_a_corrupted_stored_rate_degrades_instead_of_raising():
    """Guard 3/3. A hand-edited row must not raise DivisionByZero inside the
    SHIPPED transaction — it must look exactly like 'no rate'."""
    db = _db_with_settings({FX_UAH_PER_USD_OVERRIDE: "0", FX_UAH_PER_USD_CACHED: "junk"})

    rates = await fx_service.resolve(db)

    assert rates.is_usable is False


@pytest.mark.asyncio
async def test_override_survives_a_corrupted_cached_rate():
    db = _db_with_settings(
        {FX_UAH_PER_USD_OVERRIDE: "41.5", FX_UAH_PER_USD_CACHED: "-3"}
    )

    rates = await fx_service.resolve(db)

    assert rates.uah_per_usd == Decimal("41.5")


def test_source_url_defaults_when_unset():
    assert fx_service.get_source_url({}) == fx_service.NBU_DEFAULT_URL
    assert (
        fx_service.get_source_url({FX_SOURCE_URL: "https://bank.gov.ua/x?json"})
        == "https://bank.gov.ua/x?json"
    )


# ─── Staleness ───────────────────────────────────────────────


def test_a_fresh_auto_rate_is_not_stale():
    rates = FxRates(
        uah_per_usd=Decimal("44.6395"),
        source="nbu",
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=5),
    )
    assert rates.is_stale() is False


def test_an_old_auto_rate_is_stale():
    rates = FxRates(
        uah_per_usd=Decimal("44.6395"),
        source="nbu",
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=72),
    )
    assert rates.is_stale() is True


def test_a_manual_override_never_goes_stale():
    """The owner set it deliberately; nagging about its age is noise."""
    rates = FxRates(uah_per_usd=Decimal("41.5"), source="manual")
    assert rates.is_stale() is False


# ─── Persistence + audit ─────────────────────────────────────


@pytest.mark.asyncio
async def test_setting_a_plain_value_writes_the_value_and_an_audit_row():
    existing = AppSetting(key=FX_UAH_PER_USD_OVERRIDE, value="40.0")
    db = _db_with_settings({}, row=existing)
    actor = uuid.uuid4()

    await fx_service.set_plain_setting(
        db, FX_UAH_PER_USD_OVERRIDE, "41.5", actor_id=actor, source="manual"
    )

    assert existing.value == "41.5"
    assert existing.value_encrypted is None  # keeps the CHECK satisfied
    assert existing.updated_by_id == actor

    audit = db.add.call_args[0][0]
    assert audit.setting_key == FX_UAH_PER_USD_OVERRIDE
    assert (audit.old_value, audit.new_value) == ("40.0", "41.5")
    assert audit.source == "manual"


@pytest.mark.asyncio
async def test_clearing_deletes_the_row_and_records_it():
    """The CHECK forbids a row with neither column set, so 'clear' is a DELETE —
    and an empty string would parse as zero, which is worse than useless."""
    existing = AppSetting(key=FX_UAH_PER_USD_OVERRIDE, value="41.5")
    db = _db_with_settings({}, row=existing)
    actor = uuid.uuid4()

    removed = await fx_service.clear_plain_setting(
        db, FX_UAH_PER_USD_OVERRIDE, actor_id=actor, source="clear"
    )

    assert removed is True
    db.delete.assert_awaited_once_with(existing)
    audit = db.add.call_args[0][0]
    assert (audit.old_value, audit.new_value, audit.source) == ("41.5", None, "clear")


@pytest.mark.asyncio
async def test_clearing_an_unset_override_is_a_no_op():
    db = _db_with_settings({}, row=None)

    removed = await fx_service.clear_plain_setting(
        db, FX_UAH_PER_USD_OVERRIDE, actor_id=uuid.uuid4(), source="clear"
    )

    assert removed is False
    db.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_store_fetched_rate_writes_rate_date_and_timestamp():
    db = _db_with_settings({}, row=None)

    await fx_service.store_fetched_rate(
        db, rate=Decimal("44.6395"), rate_date=date(2026, 8, 3), actor_id=uuid.uuid4()
    )

    written = {
        c[0][0].key: c[0][0].value
        for c in db.add.call_args_list
        if isinstance(c[0][0], AppSetting)
    }
    assert written[FX_UAH_PER_USD_CACHED] == "44.6395"
    assert written[FX_RATE_DATE] == "2026-08-03"
    assert FX_FETCHED_AT in written
