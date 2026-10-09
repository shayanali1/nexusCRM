"""Development and Demo Seeding Utility.

IMPORTANT ARCHITECTURAL RULE:
This script is strictly intended for local development, demo environments, and automated testing.
In production environments, schema creation and evolution MUST be performed exclusively
via Alembic migrations:
    alembic upgrade head

This script MUST NOT be used in production to bypass migration tracking.
"""

import asyncio
import os
import sys
from alembic import command
from alembic.config import Config
from app.core.config import settings
from app.core.logging import logger
from app.seed.seed_data import seed_database

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def run_alembic_migrations():
    """Execute authoritative Alembic migrations up to head."""
    ini_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    if not os.path.exists(ini_path):
        logger.warning(f"alembic.ini not found at {ini_path}, checking current directory")
        ini_path = "alembic.ini"

    logger.info(f"Applying authoritative migrations via Alembic: {ini_path}")
    alembic_cfg = Config(ini_path)
    # Ensure sync URL is passed to config if using sqlite
    sync_url = settings.SYNC_DATABASE_URL or settings.DATABASE_URL.replace("+asyncpg", "").replace("+aiosqlite", "")
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations applied successfully.")


async def init_dev_and_seed():
    """Run migrations and seed realistic demo dataset for local dev / testing."""
    if settings.APP_ENV == "production":
        logger.error(
            "CRITICAL: db_init.py was invoked in PRODUCTION environment! "
            "Production schema MUST be updated using 'alembic upgrade head'. Aborting."
        )
        sys.exit(1)

    print("--- NexusCRM Dev Bootstrap & Seed ---")
    print(f"Environment: {settings.APP_ENV}")

    # 1. Apply Alembic migrations programmatically
    try:
        run_alembic_migrations()
    except Exception as exc:
        logger.warning(
            f"Alembic programmatic migration notice: {exc}. "
            "If using in-memory or custom dialect, ensure tables are prepared."
        )

    # 2. Run demo data seeding on migrated database
    print("Seeding initial development dataset...")
    await seed_database()
    print("--- NexusCRM Bootstrap & Seed Complete ---")


if __name__ == "__main__":
    asyncio.run(init_dev_and_seed())
