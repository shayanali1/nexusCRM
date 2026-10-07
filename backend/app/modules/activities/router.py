from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.permissions import Permission
from app.modules.activities.models import Activity
from app.modules.activities.repository import ActivityRepository
from app.modules.activities.schemas import ActivityCreate, ActivityResponse
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.users.models import User

router = APIRouter(prefix="/activities", tags=["Activities & Timeline"])


def _to_act_resp(a: Activity) -> ActivityResponse:
    resp = ActivityResponse.model_validate(a)
    if a.user:
        resp.user_name = a.user.full_name
    return resp


@router.get("", response_model=List[ActivityResponse])
async def list_activities(
    lead_id: Optional[str] = Query(None, description="Filter timeline by lead ID"),
    contact_id: Optional[str] = Query(None, description="Filter timeline by contact ID"),
    deal_id: Optional[str] = Query(None, description="Filter timeline by deal ID"),
    activity_type: Optional[str] = Query(None, description="Filter by type (CALL, EMAIL, MEETING, NOTE, PROPOSAL)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission(Permission.ACTIVITIES_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve chronological activity timeline across customer interactions."""
    repo = ActivityRepository(db, current_user.organization_id)
    activities = await repo.list_all(lead_id, contact_id, deal_id, activity_type, limit, offset)
    return [_to_act_resp(a) for a in activities]


@router.post("", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
async def log_activity(
    req: ActivityCreate,
    current_user: User = Depends(require_permission(Permission.ACTIVITIES_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    """Log an interaction (call with outcome, email, meeting notes, proposal sent)."""
    repo = ActivityRepository(db, current_user.organization_id)
    activity = await repo.create(req, user_id=current_user.id)
    return _to_act_resp(activity)
