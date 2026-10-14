from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.companies.repository import CompanyRepository
from app.modules.companies.schemas import CompanyCreate, CompanyResponse, CompanyUpdate
from app.modules.users.models import User

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.get("", response_model=List[CompanyResponse])
async def list_companies(
    search: Optional[str] = Query(None, description="Search company name, domain, industry"),
    industry: Optional[str] = Query(None, description="Filter by company industry"),
    size: Optional[str] = Query(None, description="Filter by company size"),
    city: Optional[str] = Query(None, description="Filter by company city"),
    country: Optional[str] = Query(None, description="Filter by company country"),
    sort_by: Optional[str] = Query(None, description="Sort field"),
    sort_order: Optional[str] = Query(None, description="Sort direction ('asc' or 'desc')"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission(Permission.COMPANIES_READ)),
    db: AsyncSession = Depends(get_db),
):
    """List all company accounts."""
    repo = CompanyRepository(db, current_user.organization_id)
    companies = await repo.list_all(
        search=search,
        industry=industry,
        size=size,
        city=city,
        country=country,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    return [CompanyResponse.model_validate(c) for c in companies]


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    req: CompanyCreate,
    current_user: User = Depends(require_permission(Permission.COMPANIES_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a company account."""
    repo = CompanyRepository(db, current_user.organization_id)
    company = await repo.create(req)
    return CompanyResponse.model_validate(company)


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: str,
    current_user: User = Depends(require_permission(Permission.COMPANIES_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Get single company profile."""
    repo = CompanyRepository(db, current_user.organization_id)
    company = await repo.get_by_id(company_id)
    if not company:
        raise NotFoundException("Company not found.")
    return CompanyResponse.model_validate(company)


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: str,
    req: CompanyUpdate,
    current_user: User = Depends(require_permission(Permission.COMPANIES_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    """Update company account."""
    repo = CompanyRepository(db, current_user.organization_id)
    company = await repo.get_by_id(company_id)
    if not company:
        raise NotFoundException("Company not found.")
    updated = await repo.update(company, req)
    return CompanyResponse.model_validate(updated)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: str,
    current_user: User = Depends(require_permission(Permission.COMPANIES_DELETE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a company."""
    repo = CompanyRepository(db, current_user.organization_id)
    company = await repo.get_by_id(company_id)
    if not company:
        raise NotFoundException("Company not found.")
    await repo.delete(company)
