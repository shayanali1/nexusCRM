from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.exceptions import AIProviderException, NotFoundException
from app.core.logging import logger
from app.modules.ai.factory import get_ai_provider
from app.modules.ai.models import AIInsight, InsightType
from app.modules.ai.schemas import (
    AIStatusResponse,
    DealGuidanceRequest,
    DealGuidanceResponse,
    LeadPrioritizationRequest,
    LeadSummaryRequest,
    MessageDraftRequest,
    MessageDraftResponse,
    NextActionRequest,
    AINextActionResponse,
    AIPriorityResponse,
    AISummaryResponse,
)


class AIService:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id
        self.provider = get_ai_provider()

    def get_status(self) -> AIStatusResponse:
        """Return runtime status of the active AI intelligence provider."""
        return AIStatusResponse(
            provider=self.provider.provider_name,
            model=settings.AI_MODEL if self.provider.provider_name != "mock" else "mock-context-engine",
            is_available=self.provider.is_available,
            is_mock=(self.provider.provider_name == "mock"),
            message="AI intelligence operational." if self.provider.is_available else "AI service offline/fallback active.",
        )

    async def summarize_lead(self, request: LeadSummaryRequest) -> AISummaryResponse:
        """Generate lead activity summary and cache in tenant AI insights."""
        try:
            result = await self.provider.generate_summary(request)

            # If lead_id provided, persist / update insight
            if request.lead_id:
                insight = AIInsight(
                    organization_id=self.org_id,
                    entity_type="lead",
                    entity_id=request.lead_id,
                    insight_type=InsightType.SUMMARY.value,
                    content=result.model_dump(),
                    confidence=result.confidence,
                    model_name=result.provider,
                    provider_name=self.provider.provider_name,
                )
                self.db.add(insight)
                await self.db.commit()

            return result
        except Exception as exc:
            logger.error(f"Error generating AI summary: {exc}")
            raise AIProviderException(str(exc), provider=self.provider.provider_name)

    async def prioritize_lead(self, request: LeadPrioritizationRequest) -> AIPriorityResponse:
        """Calculate explainable lead priority score."""
        try:
            result = await self.provider.prioritize_lead(request)

            if request.lead_id:
                insight = AIInsight(
                    organization_id=self.org_id,
                    entity_type="lead",
                    entity_id=request.lead_id,
                    insight_type=InsightType.PRIORITY_SCORE.value,
                    content=result.model_dump(),
                    confidence=result.confidence,
                    model_name=result.provider,
                    provider_name=self.provider.provider_name,
                )
                self.db.add(insight)
                await self.db.commit()

            return result
        except Exception as exc:
            logger.error(f"Error calculating AI priority: {exc}")
            raise AIProviderException(str(exc), provider=self.provider.provider_name)

    async def recommend_next_action(self, request: NextActionRequest) -> AINextActionResponse:
        """Recommend optimal next sales step."""
        try:
            result = await self.provider.recommend_next_action(request)

            if request.lead_id:
                insight = AIInsight(
                    organization_id=self.org_id,
                    entity_type="lead",
                    entity_id=request.lead_id,
                    insight_type=InsightType.NEXT_ACTION.value,
                    content=result.model_dump(),
                    confidence=result.confidence,
                    model_name=result.provider,
                    provider_name=self.provider.provider_name,
                )
                self.db.add(insight)
                await self.db.commit()

            return result
        except Exception as exc:
            logger.error(f"Error recommending next action: {exc}")
            raise AIProviderException(str(exc), provider=self.provider.provider_name)

    async def draft_message(self, request: MessageDraftRequest) -> MessageDraftResponse:
        """Draft tailored follow-up communication."""
        try:
            return await self.provider.draft_message(request)
        except Exception as exc:
            logger.error(f"Error drafting message: {exc}")
            raise AIProviderException(str(exc), provider=self.provider.provider_name)

    async def provide_deal_guidance(self, request: DealGuidanceRequest) -> DealGuidanceResponse:
        """Generate deal progression and win risk analysis."""
        try:
            return await self.provider.provide_deal_guidance(request)
        except Exception as exc:
            logger.error(f"Error providing deal guidance: {exc}")
            raise AIProviderException(str(exc), provider=self.provider.provider_name)
