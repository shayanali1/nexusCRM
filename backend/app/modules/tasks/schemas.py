from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.modules.tasks.models import TaskPriority, TaskStatus, TaskType


class TaskBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    task_type: TaskType = TaskType.FOLLOW_UP
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    due_date: datetime
    assigned_to_id: Optional[str] = None
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    task_type: Optional[TaskType] = None
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    assigned_to_id: Optional[str] = None


class TaskResponse(TaskBase):
    id: str
    organization_id: str
    created_by_id: Optional[str] = None
    completed_at: Optional[datetime] = None
    is_overdue: bool = False
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    # Embedded lightweight relations
    assigned_to_name: Optional[str] = None
    lead_title: Optional[str] = None
    contact_name: Optional[str] = None
    deal_title: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TaskSummaryMetrics(BaseModel):
    total_tasks: int
    overdue_count: int
    due_today_count: int
    upcoming_count: int
    completed_count: int
