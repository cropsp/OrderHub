"""OrderHub CRM — WesternBid connectivity check (WB-1 diagnostic).

Standalone, read-only probe that is INDEPENDENT of the scheduler and the
persistent system user, so it works even when the scheduler jobs are skipping.
It loads the stored WB credentials, calls the same read-only `list_sent_parcels`
the poller uses, and reports exactly one outcome:

  * credentials not configured  -> nothing to probe
  * auth / HTTP failure          -> the HTTP status code
  * reachable, empty list        -> 0 parcels
  * reachable                    -> parcel count

The credentials (api key + login) are NEVER printed — not in full, not partially.
Only URLs handled inside the client, status codes, and counts ever surface, which
mirrors the "never log credentials" rule in services/westernbid.py.

Usage:
  cd backend && python scripts/verify_wb.py [--days N]   # default window: 30 days
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running as `python scripts/verify_wb.py` from the backend root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from config import get_settings
from database import async_session_factory
from services.westernbid import (
    WB_MAX_PAGE_SIZE,
    WesternBidAPIError,
    WesternBidClient,
    load_westernbid_credentials,
)

DEFAULT_WINDOW_DAYS = 30


async def main(days: int) -> int:
    async with async_session_factory() as db:
        credentials = await load_westernbid_credentials(db)

    if credentials is None:
        print("WB credentials not configured in app_settings — nothing to probe.")
        return 0

    api_key, login = credentials  # deliberately never printed
    settings = get_settings()
    client = WesternBidClient(api_key, login, settings.WESTERNBID_BASE_URL)
    from_date = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        parcels = await client.list_sent_parcels(
            from_date=from_date, page_size=WB_MAX_PAGE_SIZE
        )
    except httpx.HTTPStatusError as exc:
        print(
            f"WB API returned HTTP {exc.response.status_code} "
            f"(likely an auth/credential problem)."
        )
        return 1
    except (httpx.HTTPError, WesternBidAPIError) as exc:
        # Never interpolate the client/headers — only the error type/message,
        # which the service is careful to keep credential-free.
        print(f"WB API call failed: {type(exc).__name__}: {exc}")
        return 1

    if not parcels:
        print(f"WB reachable — 0 sent parcels in the last {days} days (empty list).")
    else:
        print(f"WB reachable — {len(parcels)} sent parcel(s) in the last {days} days.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe WesternBid connectivity.")
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help=f"Look-back window in days (default {DEFAULT_WINDOW_DAYS}).",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.days)))
