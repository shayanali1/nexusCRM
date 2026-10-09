from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.core.logging import logger
from app.workers.celery_app import celery_app, run_async_in_worker


async def async_process_lead_summary(
    organization_id: str,
    lead_id: str,
    context: Dict[str, Any],
    session: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Underlying async implementation of lead summary generation with strict tenant isolation."""
    from sqlalchemy import select
    from app.core.exceptions import NotFoundException
    from app.modules.ai.factory import get_ai_provider
    from app.modules.ai.models import AIInsight, InsightType
    from app.modules.ai.schemas import LeadSummaryRequest
    from app.modules.leads.models import Lead

    async def _execute(db: AsyncSession) -> Dict[str, Any]:
        # 1. Enforce tenant ownership: verify lead exists and belongs strictly to organization
        lead_stmt = select(Lead).where(
            Lead.id == lead_id,
            Lead.organization_id == organization_id,
        )
        lead = (await db.execute(lead_stmt)).scalar_one_or_none()
        if not lead:
            logger.warning(
                f"Lead {lead_id} not found in organization {organization_id}. Aborting AI summary."
            )
            raise NotFoundException(f"Lead {lead_id} not found in organization {organization_id}.")

        # 2. Invoke AI Provider
        provider = get_ai_provider()
        req = LeadSummaryRequest(
            lead_id=lead_id,
            contact_name=context.get("contact_name") or lead.title or "Lead",
            company_name=context.get("company_name"),
            stage=context.get("stage") or lead.status or "New",
            estimated_value=context.get("estimated_value", lead.estimated_value or 0.0),
            notes=context.get("notes") or lead.notes,
        )
        result = await provider.generate_summary(req)

        # 3. Save or update AIInsight idempotently
        insight_stmt = select(AIInsight).where(
            AIInsight.organization_id == organization_id,
            AIInsight.entity_type == "lead",
            AIInsight.entity_id == lead_id,
            AIInsight.insight_type == InsightType.SUMMARY.value,
        )
        existing = (await db.execute(insight_stmt)).scalars().first()
        if existing:
            existing.content = {
                "summary": result.summary,
                "key_points": result.key_points,
                "sentiment": result.sentiment,
            }
            existing.confidence = result.confidence
            existing.provider_name = result.provider
            await db.commit()
            logger.info(f"Updated existing AI summary insight for lead {lead_id} in org {organization_id}")
            return result.model_dump()

        insight = AIInsight(
            organization_id=organization_id,
            entity_type="lead",
            entity_id=lead_id,
            insight_type=InsightType.SUMMARY.value,
            content={
                "summary": result.summary,
                "key_points": result.key_points,
                "sentiment": result.sentiment,
            },
            confidence=result.confidence,
            model_name="mock-model",
            provider_name=result.provider,
        )
        db.add(insight)
        await db.commit()
        logger.info(f"Saved AI summary insight for lead {lead_id} in org {organization_id}")
        return result.model_dump()

    if session:
        return await _execute(session)
    else:
        async with AsyncSessionLocal() as db:
            return await _execute(db)


@celery_app.task(
    name="app.workers.ai_jobs.process_async_lead_summary",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def process_async_lead_summary(
    organization_id: str,
    lead_id: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Asynchronously generate lead summary in the background without blocking the API."""
    logger.info(f"Processing background AI summary job for lead {lead_id} in org {organization_id}")
    return run_async_in_worker(
        async_process_lead_summary(organization_id, lead_id, context)
    )
