import asyncio
from typing import Any, Dict
from app.core.logging import logger
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.ai_jobs.process_async_lead_summary")
def process_async_lead_summary(organization_id: str, lead_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronously generate lead summary in the background without blocking the API."""
    logger.info(f"Processing background AI summary job for lead {lead_id} in org {organization_id}")
    # In background worker, invoke AIProvider
    from app.modules.ai.factory import get_ai_provider
    from app.modules.ai.schemas import LeadSummaryRequest

    provider = get_ai_provider()
    req = LeadSummaryRequest(
        lead_id=lead_id,
        contact_name=context.get("contact_name", "Lead"),
        company_name=context.get("company_name"),
        stage=context.get("stage", "New"),
        estimated_value=context.get("estimated_value", 0.0),
        notes=context.get("notes"),
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(provider.generate_summary(req))
        logger.info(f"Completed AI summary job for lead {lead_id}")
        return result.model_dump()
    finally:
        loop.close()
