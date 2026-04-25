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
                count = await sync_shop_orders(db, shop, system_user)
                if count > 0:
                    logger.info(f"Synced {count} orders for shop {shop.name}")
                # Commit changes for this shop
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
