from typing import List, Optional
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import BadRequestException
from app.modules.contacts.models import Contact
from app.modules.companies.models import Company
from app.modules.leads.models import Lead, LeadStatus
from app.modules.leads.schemas import LeadCreate, LeadUpdate
from app.modules.users.models import User

LEADS_SORT_FIELDS = {
    "title": Lead.title,
    "status": Lead.status,
    "source": Lead.source,
    "score": Lead.score,
    "priority": Lead.priority,
    "estimated_value": Lead.estimated_value,
    "created_at": Lead.created_at,
}


class LeadRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def list_all(
        self,
        status: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        search: Optional[str] = None,
        source: Optional[str] = None,
        priority: Optional[str] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Lead]:
        if min_value is not None and max_value is not None and min_value > max_value:
            raise BadRequestException("min_value cannot be greater than max_value.")

        stmt = (
            select(Lead)
            .where(Lead.organization_id == self.org_id)
            .options(
                selectinload(Lead.contact),
                selectinload(Lead.company),
                selectinload(Lead.assigned_to),
            )
        )

        if status and status.strip():
            stmt = stmt.where(Lead.status == status.strip().upper())
        if assigned_to_id and assigned_to_id.strip():
            stmt = stmt.where(Lead.assigned_to_id == assigned_to_id.strip())
        if source and source.strip():
            stmt = stmt.where(func.lower(Lead.source) == source.strip().lower())
        if priority and priority.strip():
            stmt = stmt.where(Lead.priority == priority.strip().upper())
        if min_value is not None:
            stmt = stmt.where(Lead.estimated_value >= min_value)
        if max_value is not None:
            stmt = stmt.where(Lead.estimated_value <= max_value)

        if search and search.strip():
            search_pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Lead.title.ilike(search_pattern),
                    Lead.source.ilike(search_pattern),
                )
            )

        clean_sort_by = sort_by.strip().lower() if sort_by and sort_by.strip() else None
        clean_sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else None

        if clean_sort_order is not None and clean_sort_order not in ("asc", "desc"):
            raise BadRequestException("Invalid sort order. Must be 'asc' or 'desc'.")

        if clean_sort_by is not None:
            if clean_sort_by not in LEADS_SORT_FIELDS:
                allowed = ", ".join(sorted(LEADS_SORT_FIELDS.keys()))
                raise BadRequestException(f"Invalid sort field '{clean_sort_by}'. Allowed fields: {allowed}")

            direction = clean_sort_order if clean_sort_order else ("desc" if clean_sort_by == "created_at" else "asc")
            col = LEADS_SORT_FIELDS[clean_sort_by]
            stmt = stmt.order_by(col.desc() if direction == "desc" else col.asc(), Lead.id.asc())
        elif clean_sort_order is not None:
            if clean_sort_order == "desc":
                stmt = stmt.order_by(Lead.created_at.desc(), Lead.id.asc())
            else:
                stmt = stmt.order_by(Lead.created_at.asc(), Lead.id.asc())
        else:
            stmt = stmt.order_by(Lead.created_at.desc(), Lead.id.asc())

        stmt = stmt.offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, lead_id: str) -> Optional[Lead]:
        stmt = (
            select(Lead)
            .where(Lead.id == lead_id, Lead.organization_id == self.org_id)
            .options(
                selectinload(Lead.contact),
                selectinload(Lead.company),
                selectinload(Lead.assigned_to),
                selectinload(Lead.activities),
                selectinload(Lead.tasks),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: LeadCreate) -> Lead:
        lead = Lead(
            organization_id=self.org_id,
            title=data.title,
            status=data.status.value if hasattr(data.status, "value") else str(data.status),
            source=data.source,
            score=data.score,
            priority=data.priority.value if hasattr(data.priority, "value") else str(data.priority),
            estimated_value=data.estimated_value,
            currency=data.currency,
            notes=data.notes,
            contact_id=data.contact_id,
            company_id=data.company_id,
            assigned_to_id=data.assigned_to_id,
            custom_fields=data.custom_fields,
        )
        self.db.add(lead)
        await self.db.commit()
        await self.db.refresh(lead)
        return lead

    async def update(self, lead: Lead, data: LeadUpdate) -> Lead:
        for field, value in data.model_dump(exclude_unset=True).items():
            if hasattr(value, "value"):
                value = value.value
            setattr(lead, field, value)
        await self.db.commit()
        await self.db.refresh(lead)
        return lead

    async def delete(self, lead: Lead) -> None:
        await self.db.delete(lead)
        await self.db.commit()
