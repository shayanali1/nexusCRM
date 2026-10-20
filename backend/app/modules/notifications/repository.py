from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.notifications.models import Notification


class NotificationRepository:
    def __init__(self, db: AsyncSession, organization_id: str, user_id: str):
        self.db = db
        self.org_id = organization_id
        self.user_id = user_id

    async def list_all(
        self,
        unread_only: bool = False,
        notification_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Notification]:
        stmt = (
            select(Notification)
            .where(
                Notification.organization_id == self.org_id,
                Notification.user_id == self.user_id,
            )
        )
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))

        if notification_type and notification_type.strip():
            clean_type = notification_type.strip().upper()
            stmt = stmt.where(func.upper(Notification.notification_type) == clean_type)

        stmt = (
            stmt.order_by(Notification.created_at.desc(), Notification.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_unread_count(self) -> int:
        stmt = select(func.count(Notification.id)).where(
            Notification.organization_id == self.org_id,
            Notification.user_id == self.user_id,
            Notification.is_read.is_(False),
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def get_by_id(self, notification_id: str) -> Optional[Notification]:
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.organization_id == self.org_id,
            Notification.user_id == self.user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        title: str,
        message: str,
        notification_type: str = "INFO",
        link: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Notification:
        notif = Notification(
            organization_id=self.org_id,
            user_id=self.user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            link=link,
            extra_metadata=extra_metadata or {},
        )
        self.db.add(notif)
        await self.db.commit()
        await self.db.refresh(notif)
        return notif

    async def mark_as_read(self, notification: Notification, is_read: bool = True) -> Notification:
        notification.is_read = is_read
        notification.read_at = datetime.now(timezone.utc) if is_read else None
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def mark_all_read(self) -> int:
        stmt = (
            update(Notification)
            .where(
                Notification.organization_id == self.org_id,
                Notification.user_id == self.user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def delete(self, notification: Notification) -> None:
        await self.db.delete(notification)
        await self.db.commit()
