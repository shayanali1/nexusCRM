from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.activities.models import Activity
from app.modules.activities.schemas import ActivityCreate, ActivityUpdate
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal
from app.modules.leads.models import Lead

ACTIVITIES_SORT_FIELDS = {
    "performed_at": Activity.performed_at,
    "created_at": Activity.created_at,
    "activity_type": Activity.activity_type,
    "title": Activity.title,
}


class ActivityRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def _validate_relationships(
        self,
        lead_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        deal_id: Optional[str] = None,
    ) -> None:
        """Verify referenced entities belong to the same tenant organization and exist."""
        if lead_id and lead_id.strip():
            lead_stmt = select(Lead.id).where(
                Lead.id == lead_id.strip(),
                Lead.organization_id == self.org_id,
            )
            if not (await self.db.execute(lead_stmt)).scalar_one_or_none():
                raise NotFoundException("Lead not found.")

        if contact_id and contact_id.strip():
            ct_stmt = select(Contact.id).where(
                Contact.id == contact_id.strip(),
                Contact.organization_id == self.org_id,
            )
            if not (await self.db.execute(ct_stmt)).scalar_one_or_none():
                raise NotFoundException("Contact not found.")

        if deal_id and deal_id.strip():
            d_stmt = select(Deal.id).where(
                Deal.id == deal_id.strip(),
                Deal.organization_id == self.org_id,
            )
            if not (await self.db.execute(d_stmt)).scalar_one_or_none():
                raise NotFoundException("Deal not found.")

    async def get_by_id(self, activity_id: str) -> Optional[Activity]:
        stmt = (
            select(Activity)
            .where(Activity.id == activity_id, Activity.organization_id == self.org_id)
            .options(
                selectinload(Activity.user),
                selectinload(Activity.lead),
                selectinload(Activity.contact),
                selectinload(Activity.deal),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        lead_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        deal_id: Optional[str] = None,
        activity_type: Optional[str] = None,
        user_id: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Activity]:
        if start_date and end_date and start_date > end_date:
            raise BadRequestException("Start date cannot be after end date.")

        stmt = (
            select(Activity)
            .where(Activity.organization_id == self.org_id)
            .options(
                selectinload(Activity.user),
                selectinload(Activity.lead),
                selectinload(Activity.contact),
                selectinload(Activity.deal),
            )
        )
        if lead_id and lead_id.strip():
            stmt = stmt.where(Activity.lead_id == lead_id.strip())
        if contact_id and contact_id.strip():
            stmt = stmt.where(Activity.contact_id == contact_id.strip())
        if deal_id and deal_id.strip():
            stmt = stmt.where(Activity.deal_id == deal_id.strip())
        if activity_type and activity_type.strip():
            stmt = stmt.where(Activity.activity_type == activity_type.strip().upper())
        if user_id and user_id.strip():
            stmt = stmt.where(Activity.user_id == user_id.strip())

        # Search across title, description, outcome
        if search and search.strip():
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Activity.title.ilike(term),
                    Activity.description.ilike(term),
                    Activity.outcome.ilike(term),
                )
            )

        # Date range filters on performed_at
        if start_date:
            stmt = stmt.where(Activity.performed_at >= start_date)
        if end_date:
            stmt = stmt.where(Activity.performed_at <= end_date)

        # Dynamic Sorting
        clean_sort_by = sort_by.strip().lower() if sort_by and sort_by.strip() else None
        clean_sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else None

        if clean_sort_order is not None and clean_sort_order not in ("asc", "desc"):
            raise BadRequestException("Invalid sort order. Must be 'asc' or 'desc'.")

        direction = clean_sort_order if clean_sort_order else "desc"

        if clean_sort_by is not None:
            if clean_sort_by not in ACTIVITIES_SORT_FIELDS:
                allowed = ", ".join(sorted(ACTIVITIES_SORT_FIELDS.keys()))
                raise BadRequestException(f"Invalid sort field '{clean_sort_by}'. Allowed fields: {allowed}")
            col = ACTIVITIES_SORT_FIELDS[clean_sort_by]
            stmt = stmt.order_by(col.desc() if direction == "desc" else col.asc(), Activity.id.asc())
        else:
            # Default sorting: performed_at.desc(), secondary Activity.id.asc()
            stmt = stmt.order_by(
                Activity.performed_at.desc() if direction == "desc" else Activity.performed_at.asc(),
                Activity.id.asc(),
            )

        stmt = stmt.offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: ActivityCreate, user_id: Optional[str] = None) -> Activity:
        await self._validate_relationships(
            lead_id=data.lead_id,
            contact_id=data.contact_id,
            deal_id=data.deal_id,
        )
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

    async def update(self, activity: Activity, data: ActivityUpdate) -> Activity:
        update_dict = data.model_dump(exclude_unset=True)

        if any(k in update_dict for k in ("lead_id", "contact_id", "deal_id")):
            await self._validate_relationships(
                lead_id=update_dict.get("lead_id"),
                contact_id=update_dict.get("contact_id"),
                deal_id=update_dict.get("deal_id"),
            )

        for field, value in update_dict.items():
            if hasattr(value, "value"):
                value = value.value
            setattr(activity, field, value)
        await self.db.commit()
        await self.db.refresh(activity)
        return activity

    async def delete(self, activity: Activity) -> None:
        await self.db.delete(activity)
        await self.db.commit()
