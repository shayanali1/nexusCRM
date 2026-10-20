from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.permissions import Permission
from app.modules.activities.models import Activity
from app.modules.activities.repository import ActivityRepository
from app.modules.activities.schemas import ActivityCreate, ActivityResponse, ActivityUpdate
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.users.models import User

router = APIRouter(prefix="/activities", tags=["Activities & Timeline"])


def _to_act_resp(a: Activity) -> ActivityResponse:
    resp = ActivityResponse.model_validate(a)
    if a.user:
        resp.user_name = a.user.full_name
    if a.lead:
        resp.lead_title = a.lead.title
    if a.contact:
        resp.contact_name = a.contact.full_name
    if a.deal:
        resp.deal_title = a.deal.title
    return resp


@router.get("", response_model=List[ActivityResponse])
async def list_activities(
    lead_id: Optional[str] = Query(None, description="Filter timeline by lead ID"),
    contact_id: Optional[str] = Query(None, description="Filter timeline by contact ID"),
    deal_id: Optional[str] = Query(None, description="Filter timeline by deal ID"),
    activity_type: Optional[str] = Query(None, description="Filter by type (CALL, EMAIL, MEETING, NOTE, PROPOSAL)"),
    user_id: Optional[str] = Query(None, description="Filter by user ID who logged/performed the activity"),
    search: Optional[str] = Query(None, description="Case-insensitive search across title, description, outcome"),
    sort_by: Optional[str] = Query(None, description="Sort field (performed_at, created_at, activity_type, title)"),
    sort_order: Optional[str] = Query(None, description="Sort direction (asc, desc)"),
    start_date: Optional[datetime] = Query(None, description="Filter activities performed on or after this ISO datetime"),
    end_date: Optional[datetime] = Query(None, description="Filter activities performed on or before this ISO datetime"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission(Permission.ACTIVITIES_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve chronological activity timeline across customer interactions."""
    repo = ActivityRepository(db, current_user.organization_id)
    activities = await repo.list_all(
        lead_id=lead_id,
        contact_id=contact_id,
        deal_id=deal_id,
        activity_type=activity_type,
        user_id=user_id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
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
    loaded = await repo.get_by_id(activity.id)

    from app.core.events import CRMEvent, CRMEventType, event_dispatcher
    from app.modules.activities.models import ActivityType

    await event_dispatcher.dispatch(
        CRMEvent(
            event_name=CRMEventType.ACTIVITY_CREATED,
            organization_id=current_user.organization_id,
            entity_type="activity",
            entity_id=activity.id,
            actor_id=current_user.id,
            payload={
                "activity_id": activity.id,
                "activity_type": activity.activity_type,
                "deal_id": activity.deal_id,
                "lead_id": activity.lead_id,
                "contact_id": activity.contact_id,
            },
        ),
        db,
    )

    if activity.activity_type == ActivityType.PROPOSAL.value:
        await event_dispatcher.dispatch(
            CRMEvent(
                event_name=CRMEventType.PROPOSAL_SENT,
                organization_id=current_user.organization_id,
                entity_type="activity",
                entity_id=activity.id,
                actor_id=current_user.id,
                payload={
                    "activity_id": activity.id,
                    "deal_id": activity.deal_id,
                    "lead_id": activity.lead_id,
                    "contact_id": activity.contact_id,
                },
            ),
            db,
        )

    return _to_act_resp(loaded or activity)


@router.get("/{activity_id}", response_model=ActivityResponse)
async def get_activity(
    activity_id: str,
    current_user: User = Depends(require_permission(Permission.ACTIVITIES_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single activity by ID."""
    repo = ActivityRepository(db, current_user.organization_id)
    activity = await repo.get_by_id(activity_id)
    if not activity:
        raise NotFoundException("Activity not found.")
    return _to_act_resp(activity)


@router.patch("/{activity_id}", response_model=ActivityResponse)
async def update_activity(
    activity_id: str,
    req: ActivityUpdate,
    current_user: User = Depends(require_permission(Permission.ACTIVITIES_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    """Update an activity."""
    repo = ActivityRepository(db, current_user.organization_id)
    activity = await repo.get_by_id(activity_id)
    if not activity:
        raise NotFoundException("Activity not found.")
    updated = await repo.update(activity, req)
    loaded = await repo.get_by_id(updated.id)
    return _to_act_resp(loaded or updated)


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_activity(
    activity_id: str,
    current_user: User = Depends(require_permission(Permission.ACTIVITIES_DELETE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete an activity."""
    repo = ActivityRepository(db, current_user.organization_id)
    activity = await repo.get_by_id(activity_id)
    if not activity:
        raise NotFoundException("Activity not found.")
    await repo.delete(activity)
