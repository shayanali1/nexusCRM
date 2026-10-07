import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import Base, engine
import app.models
from app.seed.seed_data import seed_database


async def init_and_seed():
    print("Creating all database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created successfully.")

    print("Running initial seed...")
    await seed_database()
    print("Init & Seed complete!")


if __name__ == "__main__":
    asyncio.run(init_and_seed())
