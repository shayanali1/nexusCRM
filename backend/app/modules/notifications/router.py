from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationResponse
from app.modules.users.models import User

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=List[NotificationResponse])
async def list_user_notifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve in-app notifications for the authenticated user."""
    stmt = (
        select(Notification)
        .where(
            Notification.organization_id == current_user.organization_id,
            Notification.user_id == current_user.id,
        )
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    return [NotificationResponse.model_validate(n) for n in result.scalars().all()]


@router.post("/mark-all-read")
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all unread notifications as read."""
    stmt = (
        update(Notification)
        .where(
            Notification.organization_id == current_user.organization_id,
            Notification.user_id == current_user.id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True, read_at=datetime.now(timezone.utc))
    )
    await db.execute(stmt)
    await db.commit()
    return {"success": True}
