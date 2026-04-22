import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os

DATABASE_URL = "postgresql+asyncpg://crm:crm_pass@localhost:5432/crm_db"

async def check():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        # Get shop id
        res = await conn.execute(text("SELECT id FROM shops WHERE name = 'LeatherCraft UA'"))
        shop = res.fetchone()
        if not shop:
            print("Shop not found")
            return
        
        shop_id = shop[0]
        print(f"Shop ID: {shop_id}")
        
        # Get status counts
        res = await conn.execute(text(f"SELECT status, count(*) FROM orders WHERE shop_id = '{shop_id}' GROUP BY status"))
        for row in res.fetchall():
            print(f"Status: {row[0]}, Count: {row[1]}")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
