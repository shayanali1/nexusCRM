from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.modules.deals.models import DealStatus


class DealBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    value: float = Field(0.0, ge=0.0)
    currency: str = "USD"
    status: DealStatus = DealStatus.OPEN
    win_probability: int = Field(50, ge=0, le=100)
    expected_close_date: Optional[datetime] = None
    notes: Optional[str] = None
    pipeline_id: str
    stage_id: str
    contact_id: Optional[str] = None
    company_id: Optional[str] = None
    assigned_to_id: Optional[str] = None
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class DealCreate(DealBase):
    pass


class DealUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    value: Optional[float] = Field(None, ge=0.0)
    currency: Optional[str] = None
    status: Optional[DealStatus] = None
    win_probability: Optional[int] = Field(None, ge=0, le=100)
    expected_close_date: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    lost_reason: Optional[str] = None
    notes: Optional[str] = None
    stage_id: Optional[str] = None
    contact_id: Optional[str] = None
    company_id: Optional[str] = None
    assigned_to_id: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None


class DealStageMoveRequest(BaseModel):
    stage_id: str
    win_probability: Optional[int] = None
    status: Optional[DealStatus] = None
    lost_reason: Optional[str] = None


class DealResponse(DealBase):
    id: str
    organization_id: str
    closed_at: Optional[datetime] = None
    lost_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Embedded lightweight relations
    stage_name: Optional[str] = None
    contact_name: Optional[str] = None
    company_name: Optional[str] = None
    assigned_to_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
