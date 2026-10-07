from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.organizations.models import Organization
from app.modules.organizations.schemas import OrganizationUpdate


class OrganizationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, org_id: str) -> Optional[Organization]:
        stmt = select(Organization).where(Organization.id == org_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, org: Organization, update_data: OrganizationUpdate) -> Organization:
        for field, value in update_data.model_dump(exclude_unset=True).items():
            setattr(org, field, value)
        await self.db.commit()
        await self.db.refresh(org)
        return org
