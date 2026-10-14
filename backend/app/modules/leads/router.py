from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.leads.schemas import LeadConvertRequest, LeadConvertResponse, LeadCreate, LeadResponse, LeadUpdate
from app.modules.leads.service import LeadService
from app.modules.users.models import User

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.get("", response_model=List[LeadResponse])
async def list_leads(
    status: Optional[str] = Query(None, description="Filter by status (NEW, CONTACTED, etc.)"),
    assigned_to_id: Optional[str] = Query(None, description="Filter by assigned sales representative"),
    search: Optional[str] = Query(None, description="Search lead title or source"),
    source: Optional[str] = Query(None, description="Filter by lead source"),
    priority: Optional[str] = Query(None, description="Filter by lead priority (LOW, MEDIUM, HIGH, URGENT)"),
    min_value: Optional[float] = Query(None, ge=0.0, description="Minimum estimated value"),
    max_value: Optional[float] = Query(None, ge=0.0, description="Maximum estimated value"),
    sort_by: Optional[str] = Query(None, description="Sort field"),
    sort_order: Optional[str] = Query(None, description="Sort direction ('asc' or 'desc')"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission(Permission.LEADS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """List all leads in the organization with filtering and search."""
    service = LeadService(db, current_user.organization_id)
    return await service.list_leads(
        status=status,
        assigned_to_id=assigned_to_id,
        search=search,
        source=source,
        priority=priority,
        min_value=min_value,
        max_value=max_value,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    req: LeadCreate,
    current_user: User = Depends(require_permission(Permission.LEADS_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new sales lead (with optional auto-created contact & company)."""
    service = LeadService(db, current_user.organization_id)
    return await service.create_lead(req)


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: str,
    current_user: User = Depends(require_permission(Permission.LEADS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full details of a specific lead."""
    service = LeadService(db, current_user.organization_id)
    return await service.get_lead(lead_id)


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: str,
    req: LeadUpdate,
    current_user: User = Depends(require_permission(Permission.LEADS_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    """Update lead status, score, priority, or fields."""
    service = LeadService(db, current_user.organization_id)
    return await service.update_lead(lead_id, req)


@router.post("/{lead_id}/convert", response_model=LeadConvertResponse)
async def convert_lead_to_deal(
    lead_id: str,
    req: LeadConvertRequest,
    current_user: User = Depends(require_permission(Permission.DEALS_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> LeadConvertResponse:
    """Convert a qualified lead to a deal in the sales pipeline."""
    service = LeadService(db, current_user.organization_id)
    return await service.convert_lead(lead_id, req)


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: str,
    current_user: User = Depends(require_permission(Permission.LEADS_DELETE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a lead record."""
    service = LeadService(db, current_user.organization_id)
    await service.delete_lead(lead_id)
