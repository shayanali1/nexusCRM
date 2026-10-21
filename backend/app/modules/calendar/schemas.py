from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CalendarEventBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    external_event_id: Optional[str] = None
    provider: str = "google"
    user_id: Optional[str] = None
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None


class CalendarEventCreate(CalendarEventBase):
    pass


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    external_event_id: Optional[str] = None
    provider: Optional[str] = None
    user_id: Optional[str] = None
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None


class CalendarEventResponse(CalendarEventBase):
    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    # Optional display fields
    lead_title: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
