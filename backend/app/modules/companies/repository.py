from typing import List, Optional
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import BadRequestException
from app.modules.companies.models import Company
from app.modules.companies.schemas import CompanyCreate, CompanyUpdate

COMPANIES_SORT_FIELDS = {
    "name": Company.name,
    "domain": Company.domain,
    "industry": Company.industry,
    "size": Company.size,
    "city": Company.city,
    "country": Company.country,
    "created_at": Company.created_at,
}


class CompanyRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def list_all(
        self,
        search: Optional[str] = None,
        industry: Optional[str] = None,
        size: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Company]:
        stmt = (
            select(Company)
            .where(Company.organization_id == self.org_id)
        )
        if industry and industry.strip():
            stmt = stmt.where(func.lower(Company.industry) == industry.strip().lower())
        if size and size.strip():
            stmt = stmt.where(func.lower(Company.size) == size.strip().lower())
        if city and city.strip():
            stmt = stmt.where(func.lower(Company.city) == city.strip().lower())
        if country and country.strip():
            stmt = stmt.where(func.lower(Company.country) == country.strip().lower())

        if search and search.strip():
            search_pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Company.name.ilike(search_pattern),
                    Company.domain.ilike(search_pattern),
                    Company.industry.ilike(search_pattern),
                )
            )

        clean_sort_by = sort_by.strip().lower() if sort_by and sort_by.strip() else None
        clean_sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else None

        if clean_sort_order is not None and clean_sort_order not in ("asc", "desc"):
            raise BadRequestException("Invalid sort order. Must be 'asc' or 'desc'.")

        if clean_sort_by is not None:
            if clean_sort_by not in COMPANIES_SORT_FIELDS:
                allowed = ", ".join(sorted(COMPANIES_SORT_FIELDS.keys()))
                raise BadRequestException(f"Invalid sort field '{clean_sort_by}'. Allowed fields: {allowed}")

            direction = clean_sort_order if clean_sort_order else ("desc" if clean_sort_by == "created_at" else "asc")
            col = COMPANIES_SORT_FIELDS[clean_sort_by]
            stmt = stmt.order_by(col.desc() if direction == "desc" else col.asc(), Company.id.asc())
        elif clean_sort_order is not None:
            if clean_sort_order == "desc":
                stmt = stmt.order_by(Company.name.desc(), Company.id.asc())
            else:
                stmt = stmt.order_by(Company.name.asc(), Company.id.asc())
        else:
            stmt = stmt.order_by(Company.name.asc(), Company.id.asc())

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
