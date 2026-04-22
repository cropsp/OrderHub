import asyncio
import uuid
from sqlalchemy import select
from database import async_session_factory
from models.user import User

async def check_users():
    async with async_session_factory() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()
        if not users:
            print("NO USERS FOUND IN DATABASE")
        for u in users:
            print(f"User: {u.email} | Role: {u.role} | Active: {u.is_active}")

if __name__ == "__main__":
    asyncio.run(check_users())
