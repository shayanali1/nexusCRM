from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.modules.leads.models import LeadPriority, LeadStatus


class LeadBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    status: LeadStatus = LeadStatus.NEW
    source: str = "Website"
    score: int = 50
    priority: LeadPriority = LeadPriority.MEDIUM
    estimated_value: float = 0.0
    currency: str = "USD"
    notes: Optional[str] = None
    contact_id: Optional[str] = None
    company_id: Optional[str] = None
    assigned_to_id: Optional[str] = None
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class LeadCreate(LeadBase):
    # Optional nested contact creation if contact does not exist
    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    company_name: Optional[str] = None


class LeadUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    status: Optional[LeadStatus] = None
    source: Optional[str] = None
    score: Optional[int] = None
    priority: Optional[LeadPriority] = None
    estimated_value: Optional[float] = None
    currency: Optional[str] = None
    notes: Optional[str] = None
    lost_reason: Optional[str] = None
    contact_id: Optional[str] = None
    company_id: Optional[str] = None
    assigned_to_id: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None


class LeadConvertRequest(BaseModel):
    deal_title: Optional[str] = None
    deal_value: Optional[float] = None
    pipeline_id: Optional[str] = None
    stage_id: Optional[str] = None


class LeadResponse(LeadBase):
    id: str
    organization_id: str
    lost_reason: Optional[str] = None
    converted_at: Optional[datetime] = None
    converted_to_deal_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Embedded lightweight relations
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    company_name: Optional[str] = None
    assigned_to_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
