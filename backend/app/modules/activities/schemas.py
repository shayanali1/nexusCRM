from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.modules.activities.models import ActivityType


class ActivityBase(BaseModel):
    activity_type: ActivityType = ActivityType.NOTE
    title: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    outcome: Optional[str] = None  # e.g., "Connected", "Left Voicemail", "Interested"
    duration_seconds: int = 0
    performed_at: Optional[datetime] = None
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class ActivityCreate(ActivityBase):
    pass


class ActivityUpdate(BaseModel):
    activity_type: Optional[ActivityType] = None
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    outcome: Optional[str] = None
    duration_seconds: Optional[int] = None
    performed_at: Optional[datetime] = None
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None
    extra_metadata: Optional[Dict[str, Any]] = None


class ActivityResponse(ActivityBase):
    id: str
    organization_id: str
    user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Embedded user / actor info
    user_name: Optional[str] = None
    lead_title: Optional[str] = None
    contact_name: Optional[str] = None
    deal_title: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
