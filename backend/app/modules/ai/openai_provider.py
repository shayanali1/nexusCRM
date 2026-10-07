import json
from typing import Optional
import httpx
from app.core.config import settings
from app.core.exceptions import AIProviderException
from app.core.logging import logger
from app.modules.ai.mock_provider import MockAIProvider
from app.modules.ai.provider import AIProvider
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


class OpenAIProvider(AIProvider):
    """OpenAI API implementation of AIProvider with graceful fallback to mock on failure."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.AI_API_KEY
        self.model = model or settings.AI_MODEL or "gpt-4o-mini"
        self._fallback_provider = MockAIProvider()

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    async def _call_openai_chat(self, prompt: str, system_prompt: str) -> str:
        """Execute a secure HTTP call to OpenAI completion API."""
        if not self.is_available:
            logger.warning("OpenAI API key missing; falling back to Mock AI.")
            raise AIProviderException("OpenAI API key not configured.", provider="openai")

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": settings.AI_TEMPERATURE,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except Exception as exc:
                logger.error(f"OpenAI API call failed: {exc}. Falling back to internal engine.")
                raise AIProviderException(f"OpenAI service error: {str(exc)}", provider="openai")

    async def generate_summary(self, request: LeadSummaryRequest) -> AISummaryResponse:
        if not self.is_available:
            return await self._fallback_provider.generate_summary(request)

        system_prompt = "You are NexusCRM Intelligence. Return a JSON object with: summary (string), sentiment (positive/neutral/cautious/urgent), key_points (list of strings), confidence (float between 0 and 1)."
        user_prompt = f"Summarize this lead:\nContact: {request.contact_name}\nCompany: {request.company_name}\nStage: {request.stage}\nValue: {request.estimated_value}\nActivities: {request.activities}\nNotes: {request.notes}"

        try:
            raw_json = await self._call_openai_chat(user_prompt, system_prompt)
            parsed = json.loads(raw_json)
            return AISummaryResponse(
                summary=parsed.get("summary", "Summary unavailable."),
                sentiment=parsed.get("sentiment", "neutral"),
                key_points=parsed.get("key_points", []),
                confidence=float(parsed.get("confidence", 0.9)),
                provider=f"openai/{self.model}",
            )
        except Exception:
            # Fallback to local mock without bringing down CRM
            return await self._fallback_provider.generate_summary(request)

    async def prioritize_lead(self, request: LeadPrioritizationRequest) -> AIPriorityResponse:
        if not self.is_available:
            return await self._fallback_provider.prioritize_lead(request)
        try:
            system_prompt = "You are NexusCRM Prioritization. Return JSON with: priority_level (LOW/MEDIUM/HIGH/URGENT), priority_score (0-100 int), reasons (list of string rationale), suggested_focus (string), confidence (float 0-1)."
            raw_json = await self._call_openai_chat(json.dumps(request.model_dump()), system_prompt)
            parsed = json.loads(raw_json)
            return AIPriorityResponse(
                priority_level=parsed.get("priority_level", "MEDIUM"),
                priority_score=int(parsed.get("priority_score", 50)),
                reasons=parsed.get("reasons", ["Score calculated."]),
                suggested_focus=parsed.get("suggested_focus", "Follow up."),
                confidence=float(parsed.get("confidence", 0.9)),
                provider=f"openai/{self.model}",
            )
        except Exception:
            return await self._fallback_provider.prioritize_lead(request)

    async def recommend_next_action(self, request: NextActionRequest) -> AINextActionResponse:
        if not self.is_available:
            return await self._fallback_provider.recommend_next_action(request)
        try:
            system_prompt = "You are NexusCRM Action Engine. Return JSON with: recommended_action (str), rationale (str), urgency (immediate/today/this_week/low), suggested_task_title (str), suggested_due_days (int), confidence (float)."
            raw_json = await self._call_openai_chat(json.dumps(request.model_dump()), system_prompt)
            parsed = json.loads(raw_json)
            return AINextActionResponse(
                recommended_action=parsed.get("recommended_action", "Follow up with customer."),
                rationale=parsed.get("rationale", "Standard pipeline progression."),
                urgency=parsed.get("urgency", "today"),
                suggested_task_title=parsed.get("suggested_task_title", "Follow up"),
                suggested_due_days=int(parsed.get("suggested_due_days", 1)),
                confidence=float(parsed.get("confidence", 0.9)),
                provider=f"openai/{self.model}",
            )
        except Exception:
            return await self._fallback_provider.recommend_next_action(request)

    async def draft_message(self, request: MessageDraftRequest) -> MessageDraftResponse:
        if not self.is_available:
            return await self._fallback_provider.draft_message(request)
        try:
            system_prompt = "You are NexusCRM Sales Drafter. Return JSON with: channel (str), subject (nullable str), body (str), call_to_action (str), confidence (float)."
            raw_json = await self._call_openai_chat(json.dumps(request.model_dump()), system_prompt)
            parsed = json.loads(raw_json)
            return MessageDraftResponse(
                channel=request.channel,
                subject=parsed.get("subject"),
                body=parsed.get("body", "Hello, following up with you."),
                call_to_action=parsed.get("call_to_action", "Let's connect."),
                confidence=float(parsed.get("confidence", 0.9)),
                provider=f"openai/{self.model}",
            )
        except Exception:
            return await self._fallback_provider.draft_message(request)

    async def provide_deal_guidance(self, request: DealGuidanceRequest) -> DealGuidanceResponse:
        if not self.is_available:
            return await self._fallback_provider.provide_deal_guidance(request)
        try:
            system_prompt = "You are NexusCRM Deal Advisory. Return JSON with: stage_health (on_track/stalled/at_risk), win_probability_estimate (int 0-100), risk_factors (list of str), recommended_tactics (list of str), confidence (float)."
            raw_json = await self._call_openai_chat(json.dumps(request.model_dump()), system_prompt)
            parsed = json.loads(raw_json)
            return DealGuidanceResponse(
                stage_health=parsed.get("stage_health", "on_track"),
                win_probability_estimate=int(parsed.get("win_probability_estimate", 50)),
                risk_factors=parsed.get("risk_factors", []),
                recommended_tactics=parsed.get("recommended_tactics", []),
                confidence=float(parsed.get("confidence", 0.9)),
                provider=f"openai/{self.model}",
            )
        except Exception:
            return await self._fallback_provider.provide_deal_guidance(request)
