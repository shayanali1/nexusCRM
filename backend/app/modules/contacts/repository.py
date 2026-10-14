from typing import List, Optional
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import BadRequestException, NotFoundException
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.contacts.schemas import ContactCreate, ContactUpdate

CONTACTS_SORT_FIELDS = {
    "last_name": Contact.last_name,
    "first_name": Contact.first_name,
    "email": Contact.email,
    "title": Contact.title,
    "lead_source": Contact.lead_source,
    "created_at": Contact.created_at,
}


class ContactRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def list_all(
        self,
        company_id: Optional[str] = None,
        lead_source: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Contact]:
        stmt = (
            select(Contact)
            .where(Contact.organization_id == self.org_id)
            .options(selectinload(Contact.company))
        )
        if company_id and company_id.strip():
            stmt = stmt.where(Contact.company_id == company_id.strip())
        if lead_source and lead_source.strip():
            stmt = stmt.where(func.lower(Contact.lead_source) == lead_source.strip().lower())
        if search and search.strip():
            search_pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Contact.first_name.ilike(search_pattern),
                    Contact.last_name.ilike(search_pattern),
                    Contact.email.ilike(search_pattern),
                    Contact.phone.ilike(search_pattern),
                )
            )

        clean_sort_by = sort_by.strip().lower() if sort_by and sort_by.strip() else None
        clean_sort_order = sort_order.strip().lower() if sort_order and sort_order.strip() else None

        if clean_sort_order is not None and clean_sort_order not in ("asc", "desc"):
            raise BadRequestException("Invalid sort order. Must be 'asc' or 'desc'.")

        if clean_sort_by is not None:
            if clean_sort_by not in CONTACTS_SORT_FIELDS:
                allowed = ", ".join(sorted(CONTACTS_SORT_FIELDS.keys()))
                raise BadRequestException(f"Invalid sort field '{clean_sort_by}'. Allowed fields: {allowed}")

            direction = clean_sort_order if clean_sort_order else ("desc" if clean_sort_by == "created_at" else "asc")
            col = CONTACTS_SORT_FIELDS[clean_sort_by]
            stmt = stmt.order_by(col.desc() if direction == "desc" else col.asc(), Contact.id.asc())
        elif clean_sort_order is not None:
            if clean_sort_order == "desc":
                stmt = stmt.order_by(Contact.last_name.desc(), Contact.first_name.desc(), Contact.id.asc())
            else:
                stmt = stmt.order_by(Contact.last_name.asc(), Contact.first_name.asc(), Contact.id.asc())
        else:
            stmt = stmt.order_by(Contact.last_name.asc(), Contact.first_name.asc(), Contact.id.asc())

        stmt = stmt.offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, contact_id: str) -> Optional[Contact]:
        stmt = (
            select(Contact)
            .where(Contact.id == contact_id, Contact.organization_id == self.org_id)
            .options(
                selectinload(Contact.company),
                selectinload(Contact.leads),
                selectinload(Contact.deals),
                selectinload(Contact.activities),
                selectinload(Contact.tasks),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: ContactCreate) -> Contact:
        if data.company_id:
            c_stmt = select(Company.id).where(Company.id == data.company_id, Company.organization_id == self.org_id)
            if not (await self.db.execute(c_stmt)).scalar_one_or_none():
                raise NotFoundException("Company not found.")

        contact = Contact(
            organization_id=self.org_id,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone=data.phone,
            title=data.title,
            lead_source=data.lead_source,
            address=data.address,
            company_id=data.company_id,
            custom_fields=data.custom_fields,
        )
        self.db.add(contact)
        await self.db.commit()
        await self.db.refresh(contact)
        return contact

    async def update(self, contact: Contact, data: ContactUpdate) -> Contact:
        update_data = data.model_dump(exclude_unset=True)
        if "company_id" in update_data and update_data["company_id"] is not None:
            c_stmt = select(Company.id).where(Company.id == update_data["company_id"], Company.organization_id == self.org_id)
            if not (await self.db.execute(c_stmt)).scalar_one_or_none():
                raise NotFoundException("Company not found.")

        for field, value in update_data.items():
            setattr(contact, field, value)
        await self.db.commit()
        await self.db.refresh(contact)
        return contact

    async def delete(self, contact: Contact) -> None:
        await self.db.delete(contact)
        await self.db.commit()
