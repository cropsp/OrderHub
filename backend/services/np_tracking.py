"""
OrderHub CRM — Nova Poshta Tracking Client (WB-TRACK-1)

A deliberately separate client from `services/nova_poshta.py`, for one reason:
**this endpoint takes no API key and must never be given one** (task rule 5).
`TrackingDocument.getStatusDocuments` returns full status for an empty
`apiKey`, verified live against the prod store on 2026-08-05. That is
load-bearing — it means delivery tracking is not tied to any shop's Nova Poshta
credentials, and works for Lamamarka Shopify, which has no NP token at all.

`NovaPoshtaTrackingClient` therefore takes **no constructor arguments**. There
is nowhere to put a key, which is the structural guarantee behind the rule;
`NovaPoshtaClient` in the sibling module demands `api_key`, so reusing it would
have re-opened exactly the door this closes.

The HTTP shape (timeout, tenacity retry on transport errors, `success: false`
→ non-retryable `NovaPoshtaAPIError`) mirrors that sibling on purpose.
"""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from services.nova_poshta import NP_API_URL, NovaPoshtaAPIError

logger = logging.getLogger(__name__)

# NP accepts at most 100 documents per call, so thirty in-flight parcels is one
# request per day (task rule 8). Never one request per parcel.
NP_TRACKING_BATCH_SIZE = 100

# Every NP timestamp arrives as Kyiv wall-clock with no offset. Proven twice on
# 2026-08-05: (a) `59500007147707` has NP DateCreated 16:36:53 against WB's own
# CreatedDate of 13:36:57Z — 16:36:57 Kyiv, four seconds apart; (b) a Homestead,
# FL delivery stamped 17:43:36 would be tomorrow in Kyiv if it were local EDT.
# `Europe/Kiev` is the spelling used everywhere else in the codebase
# (services/shopify_sync.py) — do not "fix" it to Europe/Kyiv piecemeal.
NP_TZ = ZoneInfo("Europe/Kiev")

# Four formats in one payload, none carrying an offset. Guessing this is what
# SHOPIFY-REFUNDS-followup-2 records the cost of, so each is pinned to the field
# it actually appears on.
NP_DATE_FORMATS = (
    "%d-%m-%Y %H:%M:%S",  # DateCreated, ScheduledDeliveryDate
    "%Y-%m-%d %H:%M:%S",  # TrackingUpdateDate
    "%d.%m.%Y %H:%M:%S",  # RecipientDateTime
    "%H:%M %d.%m.%Y",     # DateScan
)


def parse_np_datetime(value: str | None) -> datetime | None:
    """Parse a Nova Poshta timestamp (Kyiv wall-clock) into an aware UTC datetime.

    Returns None for anything absent or unparseable — a tracking date is never
    important enough to fail a poll over, and a silent fallback to "now" would
    corrupt the stalled signal, which is a subtraction against these very values.
    """
    if not value or not value.strip():
        return None
    raw = value.strip()
    for fmt in NP_DATE_FORMATS:
        try:
            naive = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        return naive.replace(tzinfo=NP_TZ).astimezone(timezone.utc)
    logger.warning("[NP tracking] Unparseable timestamp %r — storing NULL", raw)
    return None


def is_no_data(record: dict) -> bool:
    """True when NP returns a stub instead of a tracked parcel.

    Detected STRUCTURALLY rather than by status code. Today the stub arrives as
    `StatusCode` 80 with an empty `Status` and 9 keys instead of ~122, and **80
    appears in no published Nova Poshta status list** — not in the
    api-portal.novapost.com table (which jumps 31 → 99) and not in the
    `Common.getDocumentStatuses` directory, which is a different namespace
    (StateId, not StatusCode). Since we cannot cite what the code means, we key
    off what we can actually see: no status text and no movement date.

    This is not hypothetical. `59500007112662` returned a full code-5 record on
    the morning of 2026-08-05 and a stub the same afternoon, while WesternBid
    still listed it as `Parcel created` / `Paid`.
    """
    return not (record.get("Status") or "").strip() and not (
        record.get("TrackingUpdateDate") or ""
    ).strip()


class NovaPoshtaTrackingClient:
    """Keyless reader for `TrackingDocument.getStatusDocuments`.

    Takes no credentials, holds no credentials and has no parameter that could
    accept one.
    """

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _post(self, documents: list[dict]) -> list[dict]:
        payload = {
            # Empty on purpose — see the module docstring. This must stay a
            # literal: there is no code path that can fill it in.
            "apiKey": "",
            "modelName": "TrackingDocument",
            "calledMethod": "getStatusDocuments",
            "methodProperties": {"Documents": documents},
        }
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.post(NP_API_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            if not data.get("success"):
                errors = data.get("errors", [])
                if isinstance(errors, dict):
                    message = ", ".join(str(v) for v in errors.values())
                elif isinstance(errors, list):
                    message = ", ".join(str(e) for e in errors)
                else:
                    message = str(errors)
                raise NovaPoshtaAPIError(f"[NP tracking] Error: {message}")
            # Every response carries a per-document warning: "Please enter a
            # valid phone number from the express invoice to show full
            # information". It is a dead end and is ignored by construction —
            # WB-TRACK-1 verified it withholds none of the fields we read, and
            # that passing the order's shipping phone does not clear it.
            return data.get("data", []) or []

    async def get_status_documents(self, numbers: list[str]) -> list[dict]:
        """Fetch tracking records for many numbers, batched at 100 per request.

        The whole in-flight set is one HTTP call while it stays under the batch
        size, which is the point of the endpoint (task rule 8).
        """
        records: list[dict] = []
        for start in range(0, len(numbers), NP_TRACKING_BATCH_SIZE):
            chunk = numbers[start : start + NP_TRACKING_BATCH_SIZE]
            documents = [{"DocumentNumber": n, "Phone": ""} for n in chunk]
            records.extend(await self._post(documents))
        return records
