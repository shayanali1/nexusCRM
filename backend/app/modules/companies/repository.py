from typing import List, Optional
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.modules.companies.models import Company
from app.modules.companies.schemas import CompanyCreate, CompanyUpdate


class CompanyRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def list_all(
        self,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Company]:
        stmt = (
            select(Company)
            .where(Company.organization_id == self.org_id)
            .order_by(Company.name)
        )
        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Company.name.ilike(search_pattern),
                    Company.domain.ilike(search_pattern),
                    Company.industry.ilike(search_pattern),
                )
            )
        stmt = stmt.offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, company_id: str) -> Optional[Company]:
        stmt = (
            select(Company)
            .where(Company.id == company_id, Company.organization_id == self.org_id)
            .options(
                selectinload(Company.contacts),
                selectinload(Company.leads),
                selectinload(Company.deals),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: CompanyCreate) -> Company:
        company = Company(
            organization_id=self.org_id,
            name=data.name,
            domain=data.domain,
            industry=data.industry,
            size=data.size,
            phone=data.phone,
            website=data.website,
            address=data.address,
            city=data.city,
            country=data.country,
            custom_fields=data.custom_fields,
        )
        self.db.add(company)
        await self.db.commit()
        await self.db.refresh(company)
        return company

    async def update(self, company: Company, data: CompanyUpdate) -> Company:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(company, field, value)
        await self.db.commit()
        await self.db.refresh(company)
        return company

    async def delete(self, company: Company) -> None:
        await self.db.delete(company)
        await self.db.commit()
