from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AIStatusResponse(BaseModel):
    provider: str
    model: str
    is_available: bool
    is_mock: bool
    message: str


class LeadSummaryRequest(BaseModel):
    lead_id: Optional[str] = None
    contact_name: str
    company_name: Optional[str] = None
    stage: str
    estimated_value: float = 0.0
    activities: List[Dict[str, Any]] = Field(default_factory=list)
    notes: Optional[str] = None


class AISummaryResponse(BaseModel):
    summary: str
    sentiment: str  # positive, neutral, cautious, urgent
    key_points: List[str]
    confidence: float
    provider: str


class LeadPrioritizationRequest(BaseModel):
    lead_id: Optional[str] = None
    lead_title: str
    contact_name: str
    stage: str
    source: str
    estimated_value: float
    days_since_last_contact: int = 0
    overdue_tasks_count: int = 0
    total_activities_count: int = 0


class AIPriorityResponse(BaseModel):
    priority_level: str  # LOW, MEDIUM, HIGH, URGENT
    priority_score: int  # 0 to 100
    reasons: List[str]
    suggested_focus: str
    confidence: float
    provider: str


class NextActionRequest(BaseModel):
    lead_id: Optional[str] = None
    contact_name: str
    stage: str
    last_interaction: Optional[str] = None
    last_interaction_date: Optional[str] = None
    open_tasks: List[str] = Field(default_factory=list)


class AINextActionResponse(BaseModel):
    recommended_action: str
    rationale: str
    urgency: str  # immediate, today, this_week, low
    suggested_task_title: str
    suggested_due_days: int
    confidence: float
    provider: str


class MessageDraftRequest(BaseModel):
    recipient_name: str
    company_name: Optional[str] = None
    channel: str = "email"  # email, whatsapp, sms
    tone: str = "professional"  # professional, friendly, persuasive, concise
    context_notes: Optional[str] = None
    deal_stage: Optional[str] = None
    proposal_value: Optional[float] = None
    last_discussion_topic: Optional[str] = None


class MessageDraftResponse(BaseModel):
    channel: str
    subject: Optional[str] = None
    body: str
    call_to_action: str
    confidence: float
    provider: str


class DealGuidanceRequest(BaseModel):
    deal_title: str
    value: float
    stage: str
    days_in_current_stage: int
    activity_count: int


class DealGuidanceResponse(BaseModel):
    stage_health: str  # on_track, stalled, at_risk
    win_probability_estimate: int
    risk_factors: List[str]
    recommended_tactics: List[str]
    confidence: float
    provider: str
