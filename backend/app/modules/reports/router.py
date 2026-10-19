from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.reports.schemas import (
    DashboardOverviewResponse,
    PipelineSummaryResponse,
    WonLostPerformanceResponse,
)
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


@router.get("/pipeline-summary", response_model=PipelineSummaryResponse)
async def get_pipeline_summary(
    pipeline_id: Optional[str] = Query(None, description="Pipeline ID (defaults to default pipeline)"),
    assigned_to_id: Optional[str] = Query(None, description="Filter by salesperson"),
    start_date: Optional[datetime] = Query(None, description="Filter start date"),
    end_date: Optional[datetime] = Query(None, description="Filter end date"),
    current_user: User = Depends(require_permission(Permission.REPORTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve pipeline summary with stage breakdowns and weighted revenue forecasts."""
    service = ReportsService(db, current_user.organization_id)
    return await service.get_pipeline_summary(
        pipeline_id=pipeline_id,
        assigned_to_id=assigned_to_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/won-lost", response_model=WonLostPerformanceResponse)
async def get_won_lost_performance(
    pipeline_id: Optional[str] = Query(None, description="Filter by pipeline ID"),
    assigned_to_id: Optional[str] = Query(None, description="Filter by salesperson"),
    start_date: Optional[datetime] = Query(None, description="Filter start date"),
    end_date: Optional[datetime] = Query(None, description="Filter end date"),
    current_user: User = Depends(require_permission(Permission.REPORTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve won/lost performance metrics and win rate for closed deals in requested date range."""
    service = ReportsService(db, current_user.organization_id)
    return await service.get_won_lost_performance(
        pipeline_id=pipeline_id,
        assigned_to_id=assigned_to_id,
        start_date=start_date,
        end_date=end_date,
    )
