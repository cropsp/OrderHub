"""
OrderHub CRM — Background Scheduler
Uses APScheduler to periodically run sync tasks.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from config import get_settings
from constants import SYSTEM_USER_ID
from database import async_session_factory
from models.app_setting import FX_FETCHED_AT, FX_UAH_PER_USD_CACHED
from models.shop import Shop, ShopPlatform
from models.user import User
from models.wb_parcel import WbParcel
from services import fx_service, wb_tracking_service
from services.shopify_sync import sync_shop_orders, sync_shop_refunds
from services.westernbid import (
    WB_MAX_PAGE_SIZE,
    WesternBidClient,
    load_westernbid_credentials,
    map_wb_item as _map_wb_item,
)
import logging

logger = logging.getLogger(__name__)

# Log the "no WB credentials configured" line exactly once (task rule 6): flip
# false→true the first time we find them missing, and back to false once they
# reappear so a later removal is reported again.
_wb_missing_creds_logged = False

# The WB poll window overlaps deliberately so a transient failure self-heals on
# the next run.
WB_POLL_WINDOW_DAYS = 3

# Refund sync (SHOPIFY-REFUNDS) lookback. A rolling `updated_at` window — a refund
# bumps its order's updatedAt, so anything refunded in the last N days is re-read and
# upserted idempotently. 35 days always covers a full calendar month + margin, so a
# refund is never missed between daily runs, even across a month boundary.
REFUND_SYNC_LOOKBACK_DAYS = 35

# Log "FX refresh failed" at ERROR the first time and then stay quiet until it
# succeeds again — an NBU outage should not fill the log with one line per run.
_fx_fetch_failure_logged = False

async def run_shopify_sync():
    """Background task to sync all active Shopify stores."""
    logger.info("Starting Shopify sync job...")

    async with async_session_factory() as db:
        system_user_result = await db.execute(
            select(User).where(User.id == SYSTEM_USER_ID)
        )
        system_user = system_user_result.scalar_one_or_none()
        if system_user is None:
            logger.error(
                "System user %s not found — skipping Shopify sync. This audit "
                "principal is installed by alembic migration a1b2c3d4e5f6 and "
                "re-created by seed.py. `alembic upgrade head` only helps if a "
                "repair migration is pending; if the DB is already at head the "
                "row was deleted post-migration and must be re-inserted "
                "(INSERT ... ON CONFLICT DO NOTHING) before the next run.",
                SYSTEM_USER_ID,
            )
            return

        shops_result = await db.execute(
            select(Shop).where(Shop.is_active == True, Shop.platform == ShopPlatform.SHOPIFY)
        )
        shops = shops_result.scalars().all()

        for shop in shops:
            try:
                result = await sync_shop_orders(db, shop, system_user)

                if result.imported > 0:
                    suffix_parts = []
                    if result.products_created > 0:
                        suffix_parts.append(
                            f"+{result.products_created} "
                            f"product{'s' if result.products_created != 1 else ''}"
                        )
                    if result.variants_created > 0:
                        suffix_parts.append(
                            f"+{result.variants_created} "
                            f"variant{'s' if result.variants_created != 1 else ''}"
                        )
                    suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
                    logger.info(
                        f"Synced {result.imported} orders for shop {shop.name}{suffix}"
                    )

                if result.errors:
                    logger.warning(
                        f"Shopify sync for shop {shop.name} completed with "
                        f"{len(result.errors)} per-order error(s)"
                    )

                await db.commit()
            except Exception as e:
                logger.error(f"Failed to sync shop {shop.name}: {e}")
                await db.rollback()


async def run_shopify_refund_sync():
    """Daily job: capture Shopify refunds as dated events (SHOPIFY-REFUNDS, Model 2).

    Third scheduler job, same shape as run_shopify_sync. For each active Shopify shop it
    upserts refunds on orders updated in the last REFUND_SYNC_LOOKBACK_DAYS days — the
    window that catches refunds posted long after the order (which the 15-min order sync,
    windowed by created_at + skip-on-existing, never revisits). Idempotent; the full
    historical retro-fix runs once via the /backfill-refunds endpoint.
    """
    logger.info("Starting Shopify refund sync job...")

    async with async_session_factory() as db:
        # Migration guard, same as the other jobs: a missing system user means
        # migrations have not run, so `order_refunds` may not exist — bail loudly.
        system_user_result = await db.execute(
            select(User).where(User.id == SYSTEM_USER_ID)
        )
        if system_user_result.scalar_one_or_none() is None:
            logger.error(
                "System user %s not found — skipping Shopify refund sync (migrations "
                "not applied?).",
                SYSTEM_USER_ID,
            )
            return

        shops_result = await db.execute(
            select(Shop).where(Shop.is_active == True, Shop.platform == ShopPlatform.SHOPIFY)
        )
        shops = shops_result.scalars().all()

        updated_since = datetime.now(timezone.utc) - timedelta(days=REFUND_SYNC_LOOKBACK_DAYS)
        for shop in shops:
            try:
                summary = await sync_shop_refunds(db, shop, updated_since=updated_since)
                if summary.get("inserted"):
                    logger.info(
                        "Captured %d new refund(s) for shop %s",
                        summary["inserted"], shop.name,
                    )
                await db.commit()
            except Exception as e:
                logger.error(f"Failed to sync refunds for shop {shop.name}: {e}")
                await db.rollback()


async def run_westernbid_poll():
    """Poll WesternBid for recently-sent parcels and upsert the local mirror.

    Second scheduler job, same shape as run_shopify_sync (task rule 2). Reads
    only — never writes to WB. No credentials → single log line + no-op (rule 6).
    """
    global _wb_missing_creds_logged
    logger.info("Starting WesternBid poll job...")

    async with async_session_factory() as db:
        # Parity + migration guard (same as the Shopify job): the poll writes no
        # actor column this sprint, but a missing system user means migrations
        # have not run, so bail loudly rather than half-work.
        system_user_result = await db.execute(
            select(User).where(User.id == SYSTEM_USER_ID)
        )
        if system_user_result.scalar_one_or_none() is None:
            logger.error(
                "System user %s not found — skipping WesternBid poll. This audit "
                "principal is installed by alembic migration a1b2c3d4e5f6 and "
                "re-created by seed.py. `alembic upgrade head` only helps if a "
                "repair migration is pending; if the DB is already at head the "
                "row was deleted post-migration and must be re-inserted "
                "(INSERT ... ON CONFLICT DO NOTHING) before the next run.",
                SYSTEM_USER_ID,
            )
            return

        credentials = await load_westernbid_credentials(db)
        if credentials is None:
            if not _wb_missing_creds_logged:
                logger.info(
                    "WesternBid credentials not configured — poll is a no-op "
                    "until they are set."
                )
                _wb_missing_creds_logged = True
            return
        # Credentials present — reset so a later removal logs again.
        _wb_missing_creds_logged = False

        api_key, login = credentials
        settings = get_settings()
        client = WesternBidClient(api_key, login, settings.WESTERNBID_BASE_URL)
        from_date = datetime.now(timezone.utc) - timedelta(days=WB_POLL_WINDOW_DAYS)

        try:
            # Status value sets we already know — bounded DISTINCT queries (a
            # handful of rows, never proportional to parcel count). Anything not
            # in these sets is a newly-observed value worth logging (the WB-1
            # reconnaissance goal).
            known_statuses = set(
                (
                    await db.execute(select(WbParcel.wb_status).distinct())
                ).scalars().all()
            )
            known_payment_statuses = set(
                (
                    await db.execute(select(WbParcel.payment_status).distinct())
                ).scalars().all()
            )

            parcels = await client.list_sent_parcels(
                from_date=from_date, page_size=WB_MAX_PAGE_SIZE
            )

            seen = inserted = updated = 0
            new_statuses: set[str] = set()
            new_payment_statuses: set[str] = set()
            now = datetime.now(timezone.utc)

            for item in parcels:
                raw_id = item.get("Id")
                if not raw_id:
                    logger.warning("WesternBid parcel missing Id — skipping")
                    continue
                seen += 1
                fields = _map_wb_item(item)

                if fields["wb_status"] not in known_statuses:
                    new_statuses.add(fields["wb_status"])
                if fields["payment_status"] not in known_payment_statuses:
                    new_payment_statuses.add(fields["payment_status"])

                # Upsert on shipment_id (task rule 10): update-in-place or insert,
                # never a duplicate row.
                existing = await db.get(WbParcel, uuid.UUID(str(raw_id)))
                if existing is None:
                    db.add(WbParcel(shipment_id=uuid.UUID(str(raw_id)), **fields))
                    inserted += 1
                else:
                    for key, value in fields.items():
                        setattr(existing, key, value)
                    existing.last_seen_at = now
                    updated += 1

            await db.commit()
            logger.info(
                "WesternBid poll complete: seen=%d inserted=%d updated=%d",
                seen,
                inserted,
                updated,
            )
            # Discard the "already known" markers so we only announce genuinely
            # new values (None is a legitimate absence, not a new status).
            announce_statuses = {s for s in new_statuses if s is not None}
            announce_payments = {s for s in new_payment_statuses if s is not None}
            if announce_statuses:
                logger.info(
                    "WesternBid newly-observed Status values: %s",
                    sorted(announce_statuses),
                )
            if announce_payments:
                logger.info(
                    "WesternBid newly-observed PaymentStatus values: %s",
                    sorted(announce_payments),
                )
        except Exception as e:
            logger.error(f"WesternBid poll failed: {e}")
            await db.rollback()


async def run_wb_tracking_poll():
    """Poll Nova Poshta for delivery status of in-flight WB parcels (WB-TRACK-1).

    Fifth scheduler job, daily. Unlike `run_westernbid_poll` there is NO
    credential branch: `TrackingDocument.getStatusDocuments` needs no API key,
    which is the whole point — tracking is not tied to any shop's Nova Poshta
    credentials and works for shops that have none.

    Batched at 100 documents per request, so the ~30 parcels in flight are one
    HTTP call per day, never one call per parcel.

    The poll itself lives in `wb_tracking_service.run_poll` (WB-TRACK-2) because
    the manual refresh route calls the very same function. This job owns only
    the session, the logging and the error contract.
    """
    logger.info("Starting WB tracking poll job...")

    async with async_session_factory() as db:
        try:
            summary = await wb_tracking_service.run_poll(db)
            # Commits either way: with nothing to poll there may still be
            # aged-out retirements stamped by `select_candidates`.
            await db.commit()
            # WB-ALERTS-1: read defensively. Everything below this line is
            # LOGGING, and the commit has already happened — a missing key must
            # never turn a successful poll into a reported failure plus a
            # pointless rollback. (It did exactly that once, caught by the dev
            # smoke rather than by a test, which is why the test now asserts
            # rollback was not called.)
            alerts_opened = summary.get("alerts_opened", 0)
            alerts_resolved = summary.get("alerts_resolved", 0)

            if not summary["polled"] and not summary["missing"]:
                # Alert sync still ran — untracked parcels are never poll
                # candidates, so this branch is exactly where an
                # untracked_aging alert gets raised.
                logger.info(
                    "WB tracking poll: no parcels to track "
                    "(alerts_opened=%d alerts_resolved=%d)",
                    alerts_opened,
                    alerts_resolved,
                )
                return
            logger.info(
                "WB tracking poll complete: polled=%d created=%d changed=%d "
                "delivered=%d no_data=%d missing=%d "
                "alerts_opened=%d alerts_resolved=%d",
                summary["polled"],
                summary["created"],
                summary["changed"],
                summary["delivered"],
                summary["no_data"],
                summary["missing"],
                alerts_opened,
                alerts_resolved,
            )
        except Exception as e:
            logger.error(f"WB tracking poll failed: {e}")
            await db.rollback()


async def run_fx_rate_refresh():
    """Refresh the cached UAH/USD rate from NBU (FX-CONVERSION).

    Scheduled rather than lazy-on-read on purpose: the read path for the rate
    includes order_consumption_service, which runs INSIDE the SHIPPED transaction
    (services/order_service.py) and, via routers/shipping.py, sits between the Nova
    Poshta TTN write and the commit. A lazy fetch would let an NBU hiccup roll back
    a transition whose TTN already exists at NP. Task rule 4: the fetch must never
    block a shipment.

    Failure is always non-fatal: the cached rate stays, and conversion carries on
    with it. Only a successful fetch writes fx_fetched_at.
    """
    global _fx_fetch_failure_logged

    async with async_session_factory() as db:
        try:
            settings_map = await fx_service.load_fx_settings(db)

            # Startup fires this job immediately (see below), so a crash-restart
            # loop would otherwise hammer NBU once per boot.
            raw_fetched = settings_map.get(FX_FETCHED_AT)
            if raw_fetched:
                try:
                    last = datetime.fromisoformat(raw_fetched)
                    age_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600
                    if age_h < fx_service.FX_MIN_REFETCH_HOURS:
                        logger.debug(
                            "FX rate fetched %.1fh ago (< %sh) — skipping refresh",
                            age_h,
                            fx_service.FX_MIN_REFETCH_HOURS,
                        )
                        return
                except ValueError:
                    logger.warning("Unparseable fx_fetched_at %r — refetching", raw_fetched)

            url = fx_service.get_source_url(settings_map)
            rate, rate_date = await fx_service.fetch_nbu_rate(url)

            # Drift guard: a misplaced decimal point must not silently re-price
            # every subsequent shipment. Keep the cached value and shout.
            cached_raw = settings_map.get(FX_UAH_PER_USD_CACHED)
            fx_service.check_drift(
                rate, Decimal(cached_raw) if cached_raw else None
            )

            await fx_service.store_fetched_rate(
                db, rate=rate, rate_date=rate_date, actor_id=SYSTEM_USER_ID
            )
            await db.commit()
            _fx_fetch_failure_logged = False
            logger.info(
                "FX rate refreshed: %s UAH per 1 USD (NBU date %s)", rate, rate_date
            )
        except Exception as e:
            await db.rollback()
            if not _fx_fetch_failure_logged:
                logger.error(
                    "FX rate refresh failed: %s. The last cached rate stays in use; "
                    "set a manual override in Settings if this persists.",
                    e,
                )
                _fx_fetch_failure_logged = True


def start_scheduler():
    scheduler = AsyncIOScheduler()
    # Run every 15 minutes
    scheduler.add_job(run_shopify_sync, 'interval', minutes=15)
    # WB poller — second job, same interval. max_instances=1 + coalesce make the
    # overlap protection explicit for a job whose paginated runtime could approach
    # the interval (the Shopify job relies on the same APScheduler defaults).
    scheduler.add_job(
        run_westernbid_poll,
        'interval',
        minutes=15,
        max_instances=1,
        coalesce=True,
    )
    # Refund sync (SHOPIFY-REFUNDS) — third job, daily. A refund settles into the
    # finance net_profit KPI and the dashboard revenue card, both of which net
    # SUM(order_refunds.amount) by refund date, so up-to-a-day latency is fine and
    # a daily cadence keeps the per-shop re-scan cheap next to the 15-min sync.
    #
    # next_run_time follows the tracking and FX jobs below, for the same reason:
    # an 'interval' job first fires AFTER the interval, so without it the sync is
    # deferred a full 24 hours by every backend restart. In production it wrote
    # nothing at all between the 2026-07-27 deploy and 2026-08-06 — all 3 rows in
    # order_refunds carry created_at = 2026-07-27, from the one-off
    # /backfill-refunds retro-fix.
    #
    # LATENT, not live: Shopify reports 59.98 of returns across the last 120 days,
    # so almost nothing was actually missed. Fixed because the mechanism is real
    # and the correction is one kwarg. (The note here previously claimed refunds
    # settle into monthly partner payouts. They do not — partner_payout_service
    # dispatches to compute_net_profit_product_only / compute_revenue_items_minus_
    # fees, and neither reads order_refunds.)
    #
    # Safe to fire on every restart: sync_shop_refunds pre-loads the shop's stored
    # shopify_refund_ids and skips a known refund before any SQL, and the insert is
    # ON CONFLICT DO NOTHING on uq_order_refund_shopify_id. A re-run's whole
    # footprint is one paginated Shopify read and zero writes.
    scheduler.add_job(
        run_shopify_refund_sync,
        'interval',
        days=1,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    # Nova Poshta delivery tracking (WB-TRACK-1) — fifth job, daily. NP scans a
    # healthy parcel at least once a day (p90 of observed gaps is 1.17 days), so
    # a daily poll loses nothing, and the whole in-flight set is one request.
    #
    # next_run_time follows the FX job below, for the same reason: an 'interval'
    # job first fires AFTER the interval, so without it the poll is deferred a
    # full 24 hours by every backend restart — making tracking freshness a
    # function of how often we deploy. That was not theoretical. Between the
    # WB-TRACK-1 deploy and WB-TRACK-2 the scheduled poll never fired once in
    # production; all 77 tracking rows came from a one-off run, and the
    # monitoring page would have opened on data as old as the last restart.
    #
    # Unlike FX there is no FX_MIN_REFETCH_HOURS equivalent making the startup
    # fetch idempotent, and none is needed: a restart costs exactly one batched
    # keyless request, and `record_poll` writes an event only on an OBSERVED
    # CHANGE, so re-polling an unchanged parcel writes nothing.
    scheduler.add_job(
        run_wb_tracking_poll,
        'interval',
        days=1,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    # FX rate refresh (FX-CONVERSION) — fourth job, daily. NBU publishes one
    # official rate per banking day, so anything more frequent is wasted.
    #
    # next_run_time is deliberate: a daily interval job would otherwise leave a
    # fresh database with no rate — and therefore no COGS on USD orders — for 24
    # hours after deploy. FX_MIN_REFETCH_HOURS inside the job keeps that startup
    # fetch idempotent across restarts.
    scheduler.add_job(
        run_fx_rate_refresh,
        'interval',
        days=1,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.start()
    logger.info("Background scheduler started")
