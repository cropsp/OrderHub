"""
OrderHub CRM — Background Scheduler
Uses APScheduler to periodically run sync tasks.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from database import async_session_factory
from models.shop import Shop, ShopPlatform
from models.user import User, UserRole
from services.shopify_sync import sync_shop_orders
import logging

logger = logging.getLogger(__name__)

async def run_shopify_sync():
    """Background task to sync all active Shopify stores."""
    logger.info("Starting Shopify sync job...")
    
    # In a real app we'd have a system user or use None if service allows
    # Let's mock a system user
    system_user = User(
        id="00000000-0000-0000-0000-000000000000",
        email="system@orderhub.dev",
        role=UserRole.OWNER,
        full_name="System Syncer"
    )

    async with async_session_factory() as db:
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
