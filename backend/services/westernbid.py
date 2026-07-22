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
# WB-3: retrieve an already-generated document for an existing shipment. Read-only
# — never creates a shipment, never spends money (task rule 1).
WB_GETDOC_PATH = "/ShipmentDocument/GetDocument"

# WB-3 rule 2 — the (DocumentType, PaperSize) to request per parcel ShippingType.
# Live-proven 2026-07-22. Any ShippingType absent here (incl. NovaPoshtaGlobal,
# which has no API thermal label) is UNSUPPORTED — the caller must not guess.
LABEL_TYPE_BY_SHIPPING_TYPE: dict[str, tuple[str, str]] = {
    "NovaPost": ("NpuLabel", "Label10x15"),  # 102×102 domestic thermal
    "UPS": ("Label", "Label10x15"),
    "ParcelFromFulfillmentCenterWarehouse": ("Label", "Label10x15"),
    "ConsolidationOptimum": ("Label", "Label10x15"),
    "ConsolidationPlus": ("Label", "Label10x15"),
}


def resolve_label_type(shipping_type: str | None) -> tuple[str, str] | None:
    """Return (DocumentType, PaperSize) for a parcel ShippingType, or None when
    unsupported (NovaPoshtaGlobal or any unknown value → cabinet fallback, rule 6)."""
    if not shipping_type:
        return None
    return LABEL_TYPE_BY_SHIPPING_TYPE.get(shipping_type)

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


class WesternBidLabelNotReady(Exception):
    """GetDocument returned HTTP 400 — the requested document is not available
    yet for this shipment/DocumentType. Non-retryable (a retry gets the same 400);
    the retry predicate must NOT catch this (task WB-3 reuse note)."""

    pass


class WesternBidTransientError(Exception):
    """GetDocument returned HTTP 5xx — a server-side hiccup. Retryable."""

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


def map_wb_item(item: dict) -> dict:
    """Project a WB parcel item onto the mutable `wb_parcel` columns.

    Status fields stay raw text (task rule 4); CreatedDate is UTC-normalized
    (rule 8). Shared by the poller upsert (`scheduler.run_westernbid_poll`) and the
    WB-3 confirm upsert (`routers.shipping`) so both write an identical mirror row.
    """
    return {
        "shipping_type": item.get("ShippingType"),
        "carrier_type": item.get("CarrierType"),
        "shipping_service_type": item.get("ShippingServiceType"),
        "tracking_numbers": item.get("TrackingNumbers") or [],
        "recipient_name": item.get("RecipientName"),
        "recipient_postal_code": item.get("RecipientPostalCode"),
        "recipient_country_code": item.get("RecipientCountryCode"),
        "package": item.get("Package"),
        "payment_status": item.get("PaymentStatus"),
        "wb_status": item.get("Status"),
        "wb_created_at": normalize_wb_datetime(item.get("CreatedDate")),
    }


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

    async def search_sent_parcels(
        self,
        recipient_name: str,
        recipient_country_code: str | None,
        from_date: datetime,
        page_size: int = WB_MAX_PAGE_SIZE,
    ) -> list[dict]:
        """WB-3 candidate search: sent parcels for one recipient.

        Filters server-side by `RecipientName` (case-insensitive, honoured) plus
        `RecipientCountryCode` when known. `RecipientPhone` is deliberately NOT
        used — a live probe (2026-07-22) matched only 1/20 orders by phone versus
        20/20 by name, and WB stores a usable phone for only ~5% of parcels. A
        single recipient never spans multiple pages, so one page suffices.
        """
        params: dict = {
            "FromDate": from_date.isoformat(),
            "PageNr": 1,
            "PageSize": min(page_size, WB_MAX_PAGE_SIZE),
            "RecipientName": recipient_name,
        }
        if recipient_country_code:
            params["RecipientCountryCode"] = recipient_country_code
        envelope = await self._get(WB_SENT_PARCELS_PATH, params)
        return envelope.get("Data") or []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        # Retry transport hiccups + WB 5xx only. WesternBidLabelNotReady (400) and
        # WesternBidAPIError (other 4xx / non-PDF) are NOT listed → reraised at once.
        retry=retry_if_exception_type((httpx.HTTPError, WesternBidTransientError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def get_document(
        self, shipment_id, document_type: str, paper_size: str | None
    ) -> bytes:
        """Fetch an already-generated shipment document as raw PDF bytes (rule 1).

        Branches on HTTP status, never on the body (rule 7): 400 → not-ready
        (non-retryable), 5xx → transient (retryable), any other non-200 → business
        error. A 200 whose body is not a PDF is also a business error.
        """
        url = f"{self.base_url}{WB_API_PREFIX}{WB_GETDOC_PATH}"
        params: dict = {
            "ShipmentId": str(shipment_id),
            "DocumentType": document_type,
        }
        if paper_size:
            params["PaperSize"] = paper_size
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers=self._headers())
            # Log path + doc type + status only — headers/credentials never logged.
            logger.debug(
                "[WB API] GET %s %s/%s -> %s",
                WB_GETDOC_PATH,
                document_type,
                paper_size,
                response.status_code,
            )
            code = response.status_code
            if code == 400:
                raise WesternBidLabelNotReady(
                    f"WB GetDocument 400 for {document_type}/{paper_size}"
                )
            if 500 <= code < 600:
                raise WesternBidTransientError(f"WB GetDocument HTTP {code}")
            if code != 200:
                raise WesternBidAPIError(f"WB GetDocument HTTP {code}")
            body = response.content
            if body[:4] != b"%PDF":
                raise WesternBidAPIError(
                    f"WB GetDocument returned non-PDF for {document_type}/{paper_size}"
                )
            return body


def rank_candidates(
    parcels: list[dict],
    order_zip: str | None,
    order_created_at: datetime | None,
) -> list[dict]:
    """Rank candidate parcels for the manager picker (WB-3 rule 3 / Q4).

    Since WB exposes no order key and ignores RecipientPostalCode server-side, we
    disambiguate client-side: postal-code equality with the order first, then
    CreatedDate proximity to the order date. Pure + stable — the manager still
    confirms the pick.
    """
    def sort_key(p: dict) -> tuple[int, float]:
        zip_match = 0 if (order_zip and p.get("RecipientPostalCode") == order_zip) else 1
        created = normalize_wb_datetime(p.get("CreatedDate"))
        if created is not None and order_created_at is not None:
            proximity = abs((created - order_created_at).total_seconds())
        else:
            proximity = float("inf")
        return (zip_match, proximity)

    return sorted(parcels, key=sort_key)


async def find_candidate_parcels(
    client: "WesternBidClient",
    *,
    recipient_name: str,
    recipient_country_code: str | None,
    order_zip: str | None,
    order_created_at: datetime | None,
    from_date: datetime,
) -> list[dict]:
    """The single order→parcel matching resolver (rule 8 seam).

    Live search by name (+country) then client-side ranking. If WB is ever granted
    Balance API access, an exact order→transaction→tracking match swaps in HERE
    without touching the router or UI.
    """
    parcels = await client.search_sent_parcels(
        recipient_name, recipient_country_code, from_date
    )
    return rank_candidates(parcels, order_zip, order_created_at)
