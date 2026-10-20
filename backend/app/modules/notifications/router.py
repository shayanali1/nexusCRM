from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.modules.auth.dependencies import get_current_user
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import (
    NotificationReadUpdate,
    NotificationResponse,
    UnreadCountResponse,
)
from app.modules.users.models import User

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=List[NotificationResponse])
async def list_user_notifications(
    unread_only: bool = Query(False, description="Filter for unread notifications only"),
    notification_type: Optional[str] = Query(None, description="Filter by notification type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve in-app notifications for the authenticated user."""
    repo = NotificationRepository(db, current_user.organization_id, current_user.id)
    notifications = await repo.list_all(
        unread_only=unread_only,
        notification_type=notification_type,
        limit=limit,
        offset=offset,
    )
    return [NotificationResponse.model_validate(n) for n in notifications]


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the count of unread notifications for the authenticated user."""
    repo = NotificationRepository(db, current_user.organization_id, current_user.id)
    count = await repo.get_unread_count()
    return UnreadCountResponse(unread_count=count)


@router.post("/mark-all-read")
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all unread notifications as read."""
    repo = NotificationRepository(db, current_user.organization_id, current_user.id)
    await repo.mark_all_read()
    return {"success": True}


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def toggle_notification_read(
    notification_id: str,
    body: Optional[NotificationReadUpdate] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read or unread."""
    repo = NotificationRepository(db, current_user.organization_id, current_user.id)
    notification = await repo.get_by_id(notification_id)
    if not notification:
        raise NotFoundException("Notification not found.")
    is_read = body.is_read if body is not None else True
    updated = await repo.mark_as_read(notification, is_read=is_read)
    return NotificationResponse.model_validate(updated)


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete / dismiss a single notification."""
    repo = NotificationRepository(db, current_user.organization_id, current_user.id)
    notification = await repo.get_by_id(notification_id)
    if not notification:
        raise NotFoundException("Notification not found.")
    await repo.delete(notification)
