from typing import List, Optional
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.modules.contacts.models import Contact
from app.modules.contacts.schemas import ContactCreate, ContactUpdate


class ContactRepository:
    def __init__(self, db: AsyncSession, organization_id: str):
        self.db = db
        self.org_id = organization_id

    async def list_all(
        self,
        company_id: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Contact]:
        stmt = (
            select(Contact)
            .where(Contact.organization_id == self.org_id)
            .options(selectinload(Contact.company))
            .order_by(Contact.last_name, Contact.first_name)
        )
        if company_id:
            stmt = stmt.where(Contact.company_id == company_id)
        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Contact.first_name.ilike(search_pattern),
                    Contact.last_name.ilike(search_pattern),
                    Contact.email.ilike(search_pattern),
                    Contact.phone.ilike(search_pattern),
                )
            )
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
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(contact, field, value)
        await self.db.commit()
        await self.db.refresh(contact)
        return contact

    async def delete(self, contact: Contact) -> None:
        await self.db.delete(contact)
        await self.db.commit()
