from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_user, require_permission
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
from app.modules.ai.service import AIService
from app.modules.users.models import User

router = APIRouter(prefix="/ai", tags=["AI Intelligence"])


@router.get("/status", response_model=AIStatusResponse)
async def get_ai_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve operational status and provider information for AI layer."""
    service = AIService(db, current_user.organization_id)
    return service.get_status()


@router.post("/summary", response_model=AISummaryResponse)
async def summarize_lead(
    request: LeadSummaryRequest,
    current_user: User = Depends(require_permission(Permission.AI_USE)),
    db: AsyncSession = Depends(get_db),
):
    """Generate concise activity summary for a lead or customer."""
    service = AIService(db, current_user.organization_id)
    return await service.summarize_lead(request)


@router.post("/prioritize", response_model=AIPriorityResponse)
async def prioritize_lead(
    request: LeadPrioritizationRequest,
    current_user: User = Depends(require_permission(Permission.AI_USE)),
    db: AsyncSession = Depends(get_db),
):
    """Calculate lead priority score with explainable business rationale."""
    service = AIService(db, current_user.organization_id)
    return await service.prioritize_lead(request)


@router.post("/next-action", response_model=AINextActionResponse)
async def recommend_next_action(
    request: NextActionRequest,
    current_user: User = Depends(require_permission(Permission.AI_USE)),
    db: AsyncSession = Depends(get_db),
):
    """Get recommended next action and actionable follow-up task."""
    service = AIService(db, current_user.organization_id)
    return await service.recommend_next_action(request)


@router.post("/draft-message", response_model=MessageDraftResponse)
async def draft_message(
    request: MessageDraftRequest,
    current_user: User = Depends(require_permission(Permission.AI_USE)),
    db: AsyncSession = Depends(get_db),
):
    """Generate tailored email or WhatsApp follow-up communication."""
    service = AIService(db, current_user.organization_id)
    return await service.draft_message(request)


@router.post("/deal-guidance", response_model=DealGuidanceResponse)
async def deal_guidance(
    request: DealGuidanceRequest,
    current_user: User = Depends(require_permission(Permission.AI_USE)),
    db: AsyncSession = Depends(get_db),
):
    """Obtain deal velocity analysis, risk factors, and closing guidance."""
    service = AIService(db, current_user.organization_id)
    return await service.provide_deal_guidance(request)
