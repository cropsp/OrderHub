"""
OrderHub CRM — WesternBid Service (WB-1)

Read-only client for WesternBid's shipping API, following the conventions of
`services/nova_poshta.py`: an `httpx.AsyncClient`, a tenacity `@retry` on the
single-request method (transient HTTP errors only — never business errors), and
credentials that are NEVER logged.

Scope this sprint is exactly one public method — `list_sent_parcels` — which
walks WB's paged envelope via `HasNext`. Writes (`CreateShipment`) are
permanently out of scope (task rule 1); there is deliberately no code path here
that could reach one.

Auth is two long-lived headers, `Authorization: <api key>` + `Login: <login>`,
which together equal full account access — both are redacted from every log line
(we only ever log URL + status + page counts, never the headers, task rule 5).
"""

import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

# Path prefix under the configurable base URL (task rule 7).
WB_API_PREFIX = "/api/v1"
WB_SENT_PARCELS_PATH = "/Shipping/parcels/sent"

# Client-side rate limiter: a small pause between page requests. WB does not
# document its rate limits (the WB-1 recon goal is to discover them), so this is
# a conservative default that keeps the paginated walk polite.
WB_PAGE_DELAY_S = 0.5

# WB caps PageSize at 500.
WB_MAX_PAGE_SIZE = 500

# Retry only genuinely transient failures — mirrors nova_poshta._post. Imported
# lazily-friendly module-level so tests can neutralise the wait.
from tenacity import (  # noqa: E402
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class WesternBidAPIError(Exception):
    """Raised on a business-level WB failure. Never retryable (mirrors
    NovaPoshtaAPIError)."""

    pass


def normalize_wb_datetime(value: str | None) -> datetime | None:
    """Parse a WB timestamp and normalize it to UTC (task rule 8).

    WB's `CreatedDate` arrives with a non-UTC offset and .NET-style 7-digit
    fractional seconds (e.g. `2026-04-27T06:55:05.4328732-05:00`), which plain
    `fromisoformat` rejects on some Pythons — so trim fractional seconds to the 6
    digits `datetime` supports before parsing. A naive value (no offset) is
    assumed already-UTC.
    """
    if not value:
        return None
    trimmed = re.sub(r"(\.\d{6})\d+", r"\1", value)
    dt = datetime.fromisoformat(trimmed)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def load_westernbid_credentials(db) -> tuple[str, str] | None:
    """Decrypt the WB credential pair from `app_settings`, or None if unset.

    Missing credentials are not an error (task rule 6) — the caller no-ops. Both
    rows must be present and non-empty; a half-configured pair returns None.
    """
    from sqlalchemy import select

    from models.app_setting import (
        AppSetting,
        WESTERNBID_API_KEY,
        WESTERNBID_LOGIN,
    )
    from services.encryption_service import decrypt_value

    result = await db.execute(
        select(AppSetting).where(
            AppSetting.key.in_([WESTERNBID_API_KEY, WESTERNBID_LOGIN])
        )
    )
    by_key = {row.key: row for row in result.scalars().all()}
    api_row = by_key.get(WESTERNBID_API_KEY)
    login_row = by_key.get(WESTERNBID_LOGIN)
    if (
        not api_row
        or not api_row.value_encrypted
        or not login_row
        or not login_row.value_encrypted
    ):
        return None
    return (
        decrypt_value(api_row.value_encrypted),
        decrypt_value(login_row.value_encrypted),
    )


class WesternBidClient:
    def __init__(self, api_key: str, login: str, base_url: str):
        self.api_key = api_key
        self.login = login
        # Normalise so `base_url` + prefix join cleanly regardless of a trailing /.
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        # NEVER log this dict (task rule 5).
        return {"Authorization": self.api_key, "Login": self.login}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _get(self, path: str, params: dict) -> dict:
        """GET one page. Retries transient HTTP errors (incl. 429/5xx via
        raise_for_status); business errors raise WesternBidAPIError, un-retried."""
        url = f"{self.base_url}{WB_API_PREFIX}{path}"
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers=self._headers())
            # Log URL + status only — headers/credentials are never logged.
            logger.debug("[WB API] GET %s -> %s", path, response.status_code)
            response.raise_for_status()
            try:
                return response.json()
            except ValueError as exc:
                raise WesternBidAPIError(
                    f"[WB API] Non-JSON response from {path}"
                ) from exc

    async def list_sent_parcels(
        self,
        from_date: datetime,
        to_date: datetime | None = None,
        page_size: int = WB_MAX_PAGE_SIZE,
    ) -> list[dict]:
        """Return all sent-parcel items in the window, walking every page.

        Follows the paged envelope's `HasNext` flag rather than trusting
        `TotalPages`, and pauses `WB_PAGE_DELAY_S` between requests.
        """
        page_size = min(page_size, WB_MAX_PAGE_SIZE)
        items: list[dict] = []
        page_nr = 1
        while True:
            params = {
                "FromDate": from_date.isoformat(),
                "PageNr": page_nr,
                "PageSize": page_size,
            }
            if to_date is not None:
                params["ToDate"] = to_date.isoformat()

            envelope = await self._get(WB_SENT_PARCELS_PATH, params)
            data = envelope.get("Data") or []
            items.extend(data)

            if not envelope.get("HasNext"):
                break
            page_nr += 1
            await asyncio.sleep(WB_PAGE_DELAY_S)

        return items
