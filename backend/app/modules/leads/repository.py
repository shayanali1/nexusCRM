from typing import List, Optional
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.modules.contacts.models import Contact
from app.modules.companies.models import Company
from app.modules.leads.models import Lead, LeadStatus
from app.modules.leads.schemas import LeadCreate, LeadUpdate
from app.modules.users.models import User


class LeadRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def list_all(
        self,
        status: Optional[str] = None,
        assigned_to_id: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Lead]:
        stmt = (
            select(Lead)
            .where(Lead.organization_id == self.org_id)
            .options(
                selectinload(Lead.contact),
                selectinload(Lead.company),
                selectinload(Lead.assigned_to),
            )
            .order_by(Lead.created_at.desc())
        )

        if status:
            stmt = stmt.where(Lead.status == status.upper())
        if assigned_to_id:
            stmt = stmt.where(Lead.assigned_to_id == assigned_to_id)
        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Lead.title.ilike(search_pattern),
                    Lead.source.ilike(search_pattern),
                )
            )

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
