from abc import ABC, abstractmethod
from typing import Any, Dict
from app.modules.ai.schemas import (
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


class AIProvider(ABC):
    """Abstract Base Class for all NexusCRM AI Provider implementations."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the unique provider name (e.g. 'mock', 'openai', 'gemini')."""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and available for inference."""
        pass

    @abstractmethod
    async def generate_summary(self, request: LeadSummaryRequest) -> AISummaryResponse:
        """Generate a concise executive brief of customer/lead activity history."""
        pass

    @abstractmethod
    async def prioritize_lead(self, request: LeadPrioritizationRequest) -> AIPriorityResponse:
        """Calculate explainable lead priority score with human-readable rationale."""
        pass

    @abstractmethod
    async def recommend_next_action(self, request: NextActionRequest) -> AINextActionResponse:
        """Determine the highest leverage next action based on current state and history."""
        pass

    @abstractmethod
    async def draft_message(self, request: MessageDraftRequest) -> MessageDraftResponse:
        """Generate context-aware follow-up email or message referencing CRM data."""
        pass

    @abstractmethod
    async def provide_deal_guidance(self, request: DealGuidanceRequest) -> DealGuidanceResponse:
        """Provide deal progression insights, win probability, and risk analysis."""
        pass
