from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    organization_id: str
    title: str
    message: str
    notification_type: str
    is_read: bool
    read_at: Optional[datetime] = None
    link: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
