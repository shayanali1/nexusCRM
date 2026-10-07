from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.contacts.models import Contact
from app.modules.contacts.repository import ContactRepository
from app.modules.contacts.schemas import ContactCreate, ContactResponse, ContactUpdate
from app.modules.users.models import User

router = APIRouter(prefix="/contacts", tags=["Contacts"])


def _to_resp(c: Contact) -> ContactResponse:
    resp = ContactResponse.model_validate(c)
    if c.company:
        resp.company_name = c.company.name
    return resp


@router.get("", response_model=List[ContactResponse])
async def list_contacts(
    company_id: Optional[str] = Query(None, description="Filter by company"),
    search: Optional[str] = Query(None, description="Search contact name, email, phone"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission(Permission.CONTACTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """List all customer contacts in the organization."""
    repo = ContactRepository(db, current_user.organization_id)
    contacts = await repo.list_all(company_id, search, limit, offset)
    return [_to_resp(c) for c in contacts]


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    req: ContactCreate,
    current_user: User = Depends(require_permission(Permission.CONTACTS_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new contact."""
    repo = ContactRepository(db, current_user.organization_id)
    contact = await repo.create(req)
    loaded = await repo.get_by_id(contact.id)
    return _to_resp(loaded or contact)


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: str,
    current_user: User = Depends(require_permission(Permission.CONTACTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Get single contact profile and relationship history."""
    repo = ContactRepository(db, current_user.organization_id)
    contact = await repo.get_by_id(contact_id)
    if not contact:
        raise NotFoundException("Contact not found.")
    return _to_resp(contact)


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: str,
    req: ContactUpdate,
    current_user: User = Depends(require_permission(Permission.CONTACTS_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    """Update contact information."""
    repo = ContactRepository(db, current_user.organization_id)
    contact = await repo.get_by_id(contact_id)
    if not contact:
        raise NotFoundException("Contact not found.")
    updated = await repo.update(contact, req)
    loaded = await repo.get_by_id(updated.id)
    return _to_resp(loaded or updated)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: str,
    current_user: User = Depends(require_permission(Permission.CONTACTS_DELETE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a contact."""
    repo = ContactRepository(db, current_user.organization_id)
    contact = await repo.get_by_id(contact_id)
    if not contact:
        raise NotFoundException("Contact not found.")
    await repo.delete(contact)
