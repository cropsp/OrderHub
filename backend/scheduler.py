"""
OrderHub CRM — Background Scheduler
Uses APScheduler to periodically run sync tasks.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from constants import SYSTEM_USER_ID
from database import async_session_factory
from models.shop import Shop, ShopPlatform
from models.user import User
from services.shopify_sync import sync_shop_orders
import logging

logger = logging.getLogger(__name__)

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
                "System user %s not found — skipping Shopify sync. "
                "Run `alembic upgrade head` to install it.",
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

def start_scheduler():
    scheduler = AsyncIOScheduler()
    # Run every 15 minutes
    scheduler.add_job(run_shopify_sync, 'interval', minutes=15)
    scheduler.start()
    logger.info("Background scheduler started")
