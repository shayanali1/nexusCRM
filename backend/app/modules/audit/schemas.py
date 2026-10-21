from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class AuditLogBase(BaseModel):
    action: str = Field(..., description="Action name, e.g. lead.created, deal.won, user.login")
    entity_type: Optional[str] = Field(None, description="Entity type, e.g. lead, deal, task, activity")
    entity_id: Optional[str] = Field(None, description="Target entity ID")
    changes: Dict[str, Any] = Field(default_factory=dict, description="Metadata or payload of changes")
    ip_address: Optional[str] = Field(None, description="Client IP address")
    user_agent: Optional[str] = Field(None, description="Client user agent string")


class AuditLogCreate(AuditLogBase):
    user_id: Optional[str] = Field(None, description="Actor user ID")


class AuditLogResponse(AuditLogBase):
    id: str
    organization_id: str
    user_id: Optional[str] = None
    user_name: Optional[str] = Field(None, description="Hydrated full name of the actor user")
    user_email: Optional[str] = Field(None, description="Hydrated email of the actor user")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
