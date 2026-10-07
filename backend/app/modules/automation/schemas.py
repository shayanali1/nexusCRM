from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class AutomationActionBase(BaseModel):
    action_type: str = Field(..., description="create_task, assign_user, send_notification, create_activity")
    action_config: Dict[str, Any] = Field(default_factory=dict)
    execution_order: int = 1


class AutomationActionCreate(AutomationActionBase):
    pass


class AutomationActionResponse(AutomationActionBase):
    id: str
    rule_id: str

    model_config = ConfigDict(from_attributes=True)


class AutomationRuleBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    event_trigger: str = Field(..., description="lead.created, deal.won, deal.stage_changed, task.overdue")
    conditions: List[Dict[str, Any]] = Field(default_factory=list)
    is_active: bool = True


class AutomationRuleCreate(AutomationRuleBase):
    actions: List[AutomationActionCreate] = Field(default_factory=list)


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    event_trigger: Optional[str] = None
    conditions: Optional[List[Dict[str, Any]]] = None
    is_active: Optional[bool] = None


class AutomationRuleResponse(AutomationRuleBase):
    id: str
    organization_id: str
    actions: List[AutomationActionResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
