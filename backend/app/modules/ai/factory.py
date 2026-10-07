from functools import lru_cache
from app.core.config import settings
from app.core.logging import logger
from app.modules.ai.mock_provider import MockAIProvider
from app.modules.ai.openai_provider import OpenAIProvider
from app.modules.ai.provider import AIProvider


@lru_cache()
def get_ai_provider() -> AIProvider:
    """Instantiate and return the configured AIProvider singleton."""
    provider_type = (settings.AI_PROVIDER or "mock").lower()

    if provider_type == "openai":
        logger.info(f"Using OpenAI Provider with model: {settings.AI_MODEL}")
        return OpenAIProvider()
    elif provider_type == "mock":
        logger.info("Using default Mock AI Provider (Zero-Cost, Offline-Enabled).")
        return MockAIProvider()
    else:
        logger.warning(f"Unknown AI_PROVIDER '{provider_type}'. Defaulting to MockAIProvider.")
        return MockAIProvider()
