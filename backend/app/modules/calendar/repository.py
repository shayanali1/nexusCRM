from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.calendar.models import CalendarEvent
from app.modules.calendar.schemas import CalendarEventCreate, CalendarEventUpdate
from app.modules.contacts.models import Contact
from app.modules.deals.models import Deal
from app.modules.leads.models import Lead
from app.modules.users.models import User

CALENDAR_SORT_FIELDS = {
    "start_time": CalendarEvent.start_time,
    "end_time": CalendarEvent.end_time,
    "created_at": CalendarEvent.created_at,
    "title": CalendarEvent.title,
}


def _normalize_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class CalendarEventRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def _validate_relationships(
        self,
        lead_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        deal_id: Optional[str] = None,
        user_id: Optional[str] = None,
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

        if user_id and user_id.strip():
            u_stmt = select(User.id).where(
                User.id == user_id.strip(),
                User.organization_id == self.org_id,
                User.is_active.is_(True),
            )
            if not (await self.db.execute(u_stmt)).scalar_one_or_none():
                raise NotFoundException("User not found.")

    async def get_by_id(self, event_id: str) -> Optional[CalendarEvent]:
        stmt = (
            select(CalendarEvent)
            .where(CalendarEvent.id == event_id, CalendarEvent.organization_id == self.org_id)
            .options(selectinload(CalendarEvent.lead))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        user_id: Optional[str] = None,
        lead_id: Optional[str] = None,
        contact_id: Optional[str] = None,
        deal_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CalendarEvent]:
        if start_date and end_date and _normalize_dt(start_date) > _normalize_dt(end_date):
            raise BadRequestException("Start date cannot be after end date.")

        stmt = (
            select(CalendarEvent)
            .where(CalendarEvent.organization_id == self.org_id)
            .options(selectinload(CalendarEvent.lead))
        )
        if user_id and user_id.strip():
            stmt = stmt.where(CalendarEvent.user_id == user_id.strip())
        if lead_id and lead_id.strip():
            stmt = stmt.where(CalendarEvent.lead_id == lead_id.strip())
        if contact_id and contact_id.strip():
            stmt = stmt.where(CalendarEvent.contact_id == contact_id.strip())
        if deal_id and deal_id.strip():
            stmt = stmt.where(CalendarEvent.deal_id == deal_id.strip())

        # Agenda window filter on start_time
        if start_date:
            stmt = stmt.where(CalendarEvent.start_time >= start_date)
        if end_date:
            stmt = stmt.where(CalendarEvent.start_time <= end_date)

        # Search across title, description, and location
        if search and search.strip():
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    CalendarEvent.title.ilike(term),
                    CalendarEvent.description.ilike(term),
                    CalendarEvent.location.ilike(term),
                )
            )

        # Dynamic Sorting (default: start_time asc, secondary id asc)
        clean_sort_by = sort_by.strip().lower() if sort_by and sort_by.strip() else None
        clean_sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else None

        if clean_sort_order is not None and clean_sort_order not in ("asc", "desc"):
            raise BadRequestException("Invalid sort order. Must be 'asc' or 'desc'.")

        direction = clean_sort_order if clean_sort_order else "asc"

        if clean_sort_by is not None:
            if clean_sort_by not in CALENDAR_SORT_FIELDS:
                allowed = ", ".join(sorted(CALENDAR_SORT_FIELDS.keys()))
                raise BadRequestException(f"Invalid sort field '{clean_sort_by}'. Allowed fields: {allowed}")
            col = CALENDAR_SORT_FIELDS[clean_sort_by]
            stmt = stmt.order_by(col.desc() if direction == "desc" else col.asc(), CalendarEvent.id.asc())
        else:
            stmt = stmt.order_by(
                CalendarEvent.start_time.desc() if direction == "desc" else CalendarEvent.start_time.asc(),
                CalendarEvent.id.asc(),
            )

        stmt = stmt.offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: CalendarEventCreate) -> CalendarEvent:
        if _normalize_dt(data.end_time) <= _normalize_dt(data.start_time):
            raise BadRequestException("End time must be after start time.")

        await self._validate_relationships(
            lead_id=data.lead_id,
            contact_id=data.contact_id,
            deal_id=data.deal_id,
            user_id=data.user_id,
        )

        event = CalendarEvent(
            organization_id=self.org_id,
            user_id=data.user_id,
            lead_id=data.lead_id,
            contact_id=data.contact_id,
            deal_id=data.deal_id,
            title=data.title,
            description=data.description,
            start_time=data.start_time,
            end_time=data.end_time,
            location=data.location,
            meeting_link=data.meeting_link,
            external_event_id=data.external_event_id,
            provider=data.provider or "google",
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def update(self, event: CalendarEvent, data: CalendarEventUpdate) -> CalendarEvent:
        update_dict = data.model_dump(exclude_unset=True)

        if any(k in update_dict for k in ("lead_id", "contact_id", "deal_id", "user_id")):
            await self._validate_relationships(
                lead_id=update_dict.get("lead_id"),
                contact_id=update_dict.get("contact_id"),
                deal_id=update_dict.get("deal_id"),
                user_id=update_dict.get("user_id"),
            )

        if "start_time" in update_dict or "end_time" in update_dict:
            effective_start = update_dict.get("start_time", event.start_time)
            effective_end = update_dict.get("end_time", event.end_time)
            if _normalize_dt(effective_end) <= _normalize_dt(effective_start):
                raise BadRequestException("End time must be after start time.")

        for field, value in update_dict.items():
            setattr(event, field, value)

        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def delete(self, event: CalendarEvent) -> None:
        await self.db.delete(event)
        await self.db.commit()
