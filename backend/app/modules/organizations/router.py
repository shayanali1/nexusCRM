from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_organization, require_permission
from app.modules.organizations.models import Organization
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import OrganizationResponse, OrganizationUpdate
from app.modules.users.models import User

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.get("/current", response_model=OrganizationResponse)
async def get_current_workspace(
    current_org: Organization = Depends(get_current_organization),
):
    """Retrieve details of the active workspace organization."""
    return OrganizationResponse.model_validate(current_org)


@router.patch("/current", response_model=OrganizationResponse)
async def update_current_workspace(
    req: OrganizationUpdate,
    current_user: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update settings or metadata for the active workspace."""
    repo = OrganizationRepository(db)
    updated = await repo.update(current_org, req)
    return OrganizationResponse.model_validate(updated)
