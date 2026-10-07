from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.reports.schemas import DashboardOverviewResponse
from app.modules.reports.service import ReportsService
from app.modules.users.models import User

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])


@router.get("/dashboard", response_model=DashboardOverviewResponse)
async def get_dashboard_overview(
    current_user: User = Depends(require_permission(Permission.REPORTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full executive KPI metrics, pipeline stage distribution, and rep leaderboard."""
    service = ReportsService(db, current_user.organization_id)
    return await service.get_dashboard_overview()
