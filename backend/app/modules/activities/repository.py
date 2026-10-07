from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.modules.activities.models import Activity
from app.modules.activities.schemas import ActivityCreate


class ActivityRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def list_all(
        self,
        lead_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        deal_id: Optional[str] = None,
        activity_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Activity]:
        stmt = (
            select(Activity)
            .where(Activity.organization_id == self.org_id)
            .options(selectinload(Activity.user))
            .order_by(Activity.performed_at.desc())
        )
        if lead_id:
            stmt = stmt.where(Activity.lead_id == lead_id)
        if contact_id:
            stmt = stmt.where(Activity.contact_id == contact_id)
        if deal_id:
            stmt = stmt.where(Activity.deal_id == deal_id)
        if activity_type:
            stmt = stmt.where(Activity.activity_type == activity_type.upper())

        stmt = stmt.offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: ActivityCreate, user_id: Optional[str] = None) -> Activity:
        performed_at = data.performed_at or datetime.now(timezone.utc)
        activity = Activity(
            organization_id=self.org_id,
            user_id=user_id,
            lead_id=data.lead_id,
            contact_id=data.contact_id,
            deal_id=data.deal_id,
            activity_type=data.activity_type.value if hasattr(data.activity_type, "value") else str(data.activity_type),
            title=data.title,
            description=data.description,
            outcome=data.outcome,
            duration_seconds=data.duration_seconds,
            performed_at=performed_at,
            extra_metadata=data.extra_metadata,
        )
        self.db.add(activity)
        await self.db.commit()
        await self.db.refresh(activity)
        return activity
