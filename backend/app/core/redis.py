from typing import Optional
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.logging import logger

redis_client: Optional[aioredis.Redis] = None


async def get_redis_pool() -> Optional[aioredis.Redis]:
    """Obtain or initialize the global async Redis connection pool."""
    global redis_client
    if redis_client is None:
        try:
            redis_client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=3.0,
                socket_connect_timeout=3.0,
            )
            await redis_client.ping()
            logger.info("Connected to Redis server.")
        except Exception as exc:
            logger.warning(f"Redis is unavailable: {exc}. Application will continue in local/in-memory mode.")
            redis_client = None
    return redis_client


async def check_redis_health() -> bool:
    """Check whether Redis is reachable and responding."""
    try:
        client = await get_redis_pool()
        if client:
            return bool(await client.ping())
        return False
    except Exception:
        return False


async def close_redis() -> None:
    """Safely close the Redis connection pool."""
    global redis_client
    if redis_client is not None:
        try:
            await redis_client.close()
        except Exception:
            pass
        redis_client = None
