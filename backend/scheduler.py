"""
OrderHub CRM — Background Scheduler
Uses APScheduler to periodically run sync tasks.
"""

from datetime import datetime, timedelta, timezone
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from config import get_settings
from constants import SYSTEM_USER_ID
from database import async_session_factory
from models.shop import Shop, ShopPlatform
from models.user import User
from models.wb_parcel import WbParcel
from services.shopify_sync import sync_shop_orders
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
    scheduler.start()
    logger.info("Background scheduler started")
