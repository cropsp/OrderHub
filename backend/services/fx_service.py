"""
OrderHub CRM — FX Service (FX-CONVERSION)

One global UAH/USD rate, sourced from the NBU public API with a manual override,
so UAH-priced materials can book a COGS onto USD orders.

DIRECTION — the single most important fact in this module
─────────────────────────────────────────────────────────
NBU publishes **UAH per 1 USD** (`rate: 44.6395` means 1 USD = 44.6395 UAH). That
is a USD→UAH quote. Converting a UAH cost into USD is therefore a **DIVISION**:

    usd = uah / uah_per_usd          # 190.43 UAH / 41.5 ≈ 4.59 USD
    uah = usd * uah_per_usd

Multiplying instead would inflate a warehouse cost by ~1900x and still look like a
plausible number in a P&L. Everything here — the key names in app_settings, the
column name on Order, the dataclass field — spells out `uah_per_usd` for exactly
that reason, and tests/test_fx_direction.py pins it with a concrete figure.

We deliberately store NBU's published quote as-is rather than normalising to a
UAH→USD multiplier: the reciprocal (0.0224...) loses precision in a fixed-scale
Numeric column and cannot be checked against the published number by eye.

RESOLUTION
──────────
A manual override wins if set; otherwise the last successful NBU fetch; otherwise
nothing (`FxRates.unavailable()`). The fetch is done by a scheduled job — never on
a read path — because the read path includes the SHIPPED transaction, and an NBU
hiccup must never roll back a transition whose Nova Poshta TTN already exists.

VALIDATION — three independent guards
─────────────────────────────────────
1. ingest  — reject non-numeric / <= 0 / outside the sane band; never overwrite a
             good cached value with a rejected one.
2. drift   — reject a fetch more than FX_MAX_DRIFT_PCT away from the cached rate
             (a misplaced decimal point is 900% drift; a real currency move that
             large is what the manual override is for).
3. use     — resolve() re-validates before anything divides, so a hand-edited DB
             row degrades to "no rate" instead of raising DivisionByZero inside
             the ship transaction.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from models.app_setting import (
    FX_FETCHED_AT,
    FX_RATE_DATE,
    FX_SOURCE_URL,
    FX_UAH_PER_USD_CACHED,
    FX_UAH_PER_USD_OVERRIDE,
    AppSetting,
)
from models.fx_rate_audit import FxRateAudit

logger = logging.getLogger(__name__)


# ── Configuration ──────────────────────────────────────────────────────────

NBU_DEFAULT_URL = (
    "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&json"
)

# The source URL is operator-editable (task rule 2), which makes it an SSRF
# surface: the backend fetches it server-side. Constrain it to NBU over TLS.
FX_ALLOWED_SCHEME = "https"
FX_ALLOWED_HOST = "bank.gov.ua"

# Sane band for a UAH-per-USD quote. Wide enough to survive years of drift, tight
# enough to reject a zero, a negative, or a units mix-up.
FX_MIN_UAH_PER_USD = Decimal("1")
FX_MAX_UAH_PER_USD = Decimal("1000")

# Reject a fetch this far from the cached rate. A misplaced decimal point is 900%;
# a genuine >25% single-day move is rare and is what the manual override exists for.
FX_MAX_DRIFT_PCT = Decimal("25")

# The refresh job runs daily, so two consecutive misses is the point at which the
# settings card should say so out loud. Advisory only — a stale rate still books.
FX_STALE_AFTER_HOURS = 48

# The job also fires once at startup (see scheduler.py). Without this floor, a
# crash-restart loop would hammer NBU on every boot.
FX_MIN_REFETCH_HOURS = 6

# The currency pair this module knows. Anything else degrades (task rule 1).
BASE_CURRENCY = "UAH"
QUOTE_CURRENCY = "USD"


class FxFetchError(Exception):
    """NBU returned something unusable. Never overwrites the cached rate."""


class FxUnsupported(Exception):
    """Asked to convert a pair we have no rate for. Callers degrade, never crash."""


def normalize_currency(value: str | None) -> str:
    """Currency codes are bare String(3) with no CHECK anywhere (models/material.py,
    models/order.py), so they become dispatch keys only after normalising. A stray
    'uah ' must not silently become an unknown pair."""
    return (value or "").strip().upper()


# ── Resolved state ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FxRates:
    """Resolved FX state. Never a None sentinel — `unavailable()` is the empty
    form, mirroring access_service.CapabilitySet / ShopScope.

    `uah_per_usd` is NBU's quote direction: UAH per 1 USD. It is already
    band-validated by resolve(), so `convert` can divide without re-checking.
    """

    uah_per_usd: Decimal | None = None
    source: str | None = None  # "manual" | "nbu"
    rate_date: date | None = None  # NBU exchangedate; None for a manual override
    fetched_at: datetime | None = None  # last successful NBU fetch

    @classmethod
    def unavailable(cls) -> "FxRates":
        return cls()

    @property
    def is_usable(self) -> bool:
        return self.uah_per_usd is not None

    def is_stale(self, *, now: datetime | None = None) -> bool:
        """Advisory freshness flag for the settings UI. A manual override never
        goes stale (the owner set it deliberately); an auto rate with no fetch
        timestamp counts as stale."""
        if self.source == "manual":
            return False
        if self.fetched_at is None:
            return self.is_usable
        now = now or datetime.now(timezone.utc)
        age_hours = (now - self.fetched_at).total_seconds() / 3600
        return age_hours > FX_STALE_AFTER_HOURS

    def can_convert(self, *, frm: str, to: str) -> bool:
        frm, to = normalize_currency(frm), normalize_currency(to)
        if frm == to:
            # Same currency needs no rate at all — this is the KoraKlenu path.
            return bool(frm)
        if not self.is_usable:
            return False
        return {frm, to} == {BASE_CURRENCY, QUOTE_CURRENCY}

    def rate_for(self, *, frm: str, to: str) -> Decimal | None:
        """The rate that would be stamped onto an order for this conversion.

        None means "no conversion was applied" (same currency), NOT "no rate
        available" — callers only reach here after can_convert() said yes.
        """
        frm, to = normalize_currency(frm), normalize_currency(to)
        if frm == to:
            return None
        return self.uah_per_usd

    def convert(self, amount: Decimal, *, frm: str, to: str) -> Decimal:
        """Convert `amount`. Returns an UNROUNDED Decimal on purpose — callers
        quantize once at the end of their fold, never per line or per bucket.

        Raises FxUnsupported for any pair this module does not know, so a silent
        wrong number is impossible.
        """
        frm, to = normalize_currency(frm), normalize_currency(to)
        if frm == to and frm:
            return amount
        if not self.can_convert(frm=frm, to=to):
            raise FxUnsupported(f"No {frm}->{to} rate available")

        rate = self.uah_per_usd
        if frm == BASE_CURRENCY and to == QUOTE_CURRENCY:
            return amount / rate  # UAH -> USD is DIVISION. See module docstring.
        return amount * rate  # USD -> UAH


def _validate_rate(raw: object) -> Decimal:
    """Guard 1/3 (ingest) and guard 3/3 (use). Raises FxFetchError."""
    try:
        rate = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FxFetchError(f"Rate is not a number: {raw!r}") from exc
    if not rate.is_finite():
        raise FxFetchError(f"Rate is not finite: {raw!r}")
    if not (FX_MIN_UAH_PER_USD <= rate <= FX_MAX_UAH_PER_USD):
        raise FxFetchError(
            f"Rate {rate} outside the sane band "
            f"[{FX_MIN_UAH_PER_USD}, {FX_MAX_UAH_PER_USD}]"
        )
    return rate


def check_drift(new_rate: Decimal, cached_rate: Decimal | None) -> None:
    """Guard 2/3. Raises FxFetchError if `new_rate` moved too far from the cache."""
    if cached_rate is None or cached_rate == 0:
        return
    drift_pct = abs(new_rate - cached_rate) / cached_rate * Decimal("100")
    if drift_pct > FX_MAX_DRIFT_PCT:
        raise FxFetchError(
            f"Rate {new_rate} differs from cached {cached_rate} by "
            f"{drift_pct.quantize(Decimal('0.01'))}% (limit {FX_MAX_DRIFT_PCT}%) — "
            f"keeping the cached value. Set a manual override if this move is real."
        )


# ── NBU source ─────────────────────────────────────────────────────────────


def validate_source_url(url: str) -> str:
    """The URL is owner-editable, and the backend fetches it server-side. Restrict
    it to NBU over TLS so the setting is not a general-purpose SSRF primitive."""
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != FX_ALLOWED_SCHEME:
        raise ValueError(f"FX source URL must use {FX_ALLOWED_SCHEME}://")
    host = (parsed.hostname or "").lower()
    if host != FX_ALLOWED_HOST and not host.endswith(f".{FX_ALLOWED_HOST}"):
        raise ValueError(f"FX source URL host must be {FX_ALLOWED_HOST}")
    return url


def parse_nbu_response(body: str) -> tuple[Decimal, date | None]:
    """Parse NBU's exchange payload. Probed live 2026-08-02:

        [{"r030":840,"txt":"Долар США","rate":44.6395,"cc":"USD",
          "exchangedate":"03.08.2026","special":"N"}]

    Three shape facts this has to survive, all verified against the live endpoint:
      * the body is a LIST even for a single valcode;
      * an unknown valcode returns HTTP 200 with `[]` — an empty list is a FETCH
        FAILURE, never a rate of 0;
      * the URL is operator-editable, and dropping `valcode` returns ~40 currencies
        with DZD first — so we match on `cc`, never on element [0].

    `exchangedate` is DD.MM.YYYY and is the *next banking day* (probed 2026-08-02,
    returned 03.08.2026), so it is stored separately from our fetch timestamp.
    """
    try:
        # parse_float=Decimal keeps the published digits exact — never round-trip
        # money-adjacent numbers through a binary float.
        payload = json.loads(body, parse_float=Decimal)
    except ValueError as exc:
        raise FxFetchError(f"FX source returned non-JSON: {body[:120]!r}") from exc

    if not isinstance(payload, list):
        raise FxFetchError(f"Expected a JSON list, got {type(payload).__name__}")
    if not payload:
        raise FxFetchError(
            "FX source returned an empty list — check the valcode in the source URL"
        )

    row = next(
        (
            r
            for r in payload
            if isinstance(r, dict)
            and normalize_currency(r.get("cc")) == QUOTE_CURRENCY
        ),
        None,
    )
    if row is None:
        raise FxFetchError(
            f"No {QUOTE_CURRENCY} row in the FX response "
            f"(got: {[r.get('cc') for r in payload if isinstance(r, dict)][:5]})"
        )

    rate = _validate_rate(row.get("rate"))

    rate_date: date | None = None
    raw_date = row.get("exchangedate")
    if raw_date:
        try:
            rate_date = datetime.strptime(str(raw_date), "%d.%m.%Y").date()
        except ValueError:
            # Non-fatal: the rate is the payload, the date is provenance.
            logger.warning("[FX] Unparseable exchangedate %r — storing none", raw_date)

    return rate, rate_date


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(httpx.HTTPError),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def fetch_nbu_rate(url: str) -> tuple[Decimal, date | None]:
    """Fetch + parse one rate. Follows the services/nova_poshta.py convention:
    per-call client, tenacity on transport errors only.

    Note FxFetchError is deliberately NOT retried — a malformed body will be just
    as malformed three seconds later, and retrying it only delays the log line.
    """
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return parse_nbu_response(response.text)


# ── Settings access ────────────────────────────────────────────────────────

_FX_KEYS = (
    FX_SOURCE_URL,
    FX_UAH_PER_USD_OVERRIDE,
    FX_UAH_PER_USD_CACHED,
    FX_RATE_DATE,
    FX_FETCHED_AT,
)


async def load_fx_settings(db: AsyncSession) -> dict[str, str]:
    """All FX rows in one round trip. Missing keys are simply absent."""
    result = await db.execute(
        select(AppSetting.key, AppSetting.value).where(AppSetting.key.in_(_FX_KEYS))
    )
    return {k: v for k, v in result.all() if v is not None}


def get_source_url(settings: dict[str, str]) -> str:
    return settings.get(FX_SOURCE_URL) or NBU_DEFAULT_URL


def _parse_stored_rate(raw: str | None, *, label: str) -> Decimal | None:
    """Guard 3/3 (use): a hand-edited or corrupted row degrades to None rather
    than exploding inside the SHIPPED transaction."""
    if raw is None:
        return None
    try:
        return _validate_rate(raw)
    except FxFetchError as exc:
        logger.error("[FX] Stored %s is unusable (%s) — treating as unset", label, exc)
        return None


async def resolve(db: AsyncSession) -> FxRates:
    """Resolve the effective rate. Manual override wins, else the cached NBU rate,
    else unavailable. Pure read — never fetches (task rule 4)."""
    settings = await load_fx_settings(db)

    override = _parse_stored_rate(
        settings.get(FX_UAH_PER_USD_OVERRIDE), label="manual override"
    )
    if override is not None:
        return FxRates(uah_per_usd=override, source="manual")

    cached = _parse_stored_rate(
        settings.get(FX_UAH_PER_USD_CACHED), label="cached NBU rate"
    )
    if cached is None:
        return FxRates.unavailable()

    rate_date: date | None = None
    if raw_date := settings.get(FX_RATE_DATE):
        try:
            rate_date = date.fromisoformat(raw_date)
        except ValueError:
            logger.warning("[FX] Unparseable stored rate_date %r", raw_date)

    fetched_at: datetime | None = None
    if raw_fetched := settings.get(FX_FETCHED_AT):
        try:
            fetched_at = datetime.fromisoformat(raw_fetched)
        except ValueError:
            logger.warning("[FX] Unparseable stored fetched_at %r", raw_fetched)

    return FxRates(
        uah_per_usd=cached, source="nbu", rate_date=rate_date, fetched_at=fetched_at
    )


async def get_setting_row(db: AsyncSession, key: str) -> AppSetting | None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    return result.scalar_one_or_none()


async def set_plain_setting(
    db: AsyncSession,
    key: str,
    value: str,
    *,
    actor_id: uuid.UUID,
    source: str,
) -> None:
    """Upsert a NON-SECRET setting and record the change.

    Deliberately separate from routers/app_settings.py `_upsert_setting`, which
    Fernet-encrypts and stamps `last4`. Reusing that here would encrypt a public
    exchange rate and put COGS booking at the mercy of ENCRYPTION_KEY rotation.
    Flush-only — the caller owns the commit.
    """
    row = await get_setting_row(db, key)
    old_value = row.value if row is not None else None
    if row is None:
        row = AppSetting(key=key)
        db.add(row)
    row.value = value
    row.value_encrypted = None  # keep the CHECK satisfied
    row.updated_by_id = actor_id
    record_audit(
        db,
        actor_id=actor_id,
        setting_key=key,
        old_value=old_value,
        new_value=value,
        source=source,
    )


async def clear_plain_setting(
    db: AsyncSession, key: str, *, actor_id: uuid.UUID, source: str
) -> bool:
    """Delete a non-secret setting row, recording the change.

    Clearing DELETES rather than nulling: the CHECK constraint
    `num_nonnulls(value, value_encrypted) = 1` forbids a row with neither set, and
    an empty string would parse as a hard error or, worse, as zero. Returns True
    if a row was actually removed (revoke symmetry with set_plain_setting).
    """
    row = await get_setting_row(db, key)
    if row is None:
        return False
    old_value = row.value
    await db.delete(row)
    record_audit(
        db,
        actor_id=actor_id,
        setting_key=key,
        old_value=old_value,
        new_value=None,
        source=source,
    )
    return True


def record_audit(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID,
    setting_key: str,
    old_value: str | None,
    new_value: str | None,
    source: str,
) -> None:
    """Append one FxRateAudit row. Flush-only; the caller owns the commit."""
    db.add(
        FxRateAudit(
            id=uuid.uuid4(),
            actor_id=actor_id,
            setting_key=setting_key,
            old_value=old_value,
            new_value=new_value,
            source=source,
        )
    )


async def store_fetched_rate(
    db: AsyncSession,
    *,
    rate: Decimal,
    rate_date: date | None,
    actor_id: uuid.UUID,
) -> None:
    """Persist a validated NBU fetch. `fx_fetched_at` is written ONLY here — i.e.
    only on success — so staleness is measured from the last good fetch, not the
    last attempt. Flush-only; the caller owns the commit."""
    await set_plain_setting(
        db, FX_UAH_PER_USD_CACHED, str(rate), actor_id=actor_id, source="nbu"
    )
    if rate_date is not None:
        await set_plain_setting(
            db,
            FX_RATE_DATE,
            rate_date.isoformat(),
            actor_id=actor_id,
            source="nbu",
        )
    await set_plain_setting(
        db,
        FX_FETCHED_AT,
        datetime.now(timezone.utc).isoformat(),
        actor_id=actor_id,
        source="nbu",
    )
