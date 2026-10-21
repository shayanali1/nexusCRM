from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.permissions import Permission
from app.modules.auth.dependencies import require_permission
from app.modules.calendar.models import CalendarEvent
from app.modules.calendar.repository import CalendarEventRepository
from app.modules.calendar.schemas import (
    CalendarEventCreate,
    CalendarEventResponse,
    CalendarEventUpdate,
)
from app.modules.users.models import User

router = APIRouter(prefix="/calendar", tags=["Calendar"])


def _to_event_resp(event: CalendarEvent) -> CalendarEventResponse:
    resp = CalendarEventResponse.model_validate(event)
    if event.lead:
        resp.lead_title = event.lead.title
    return resp


@router.get("", response_model=List[CalendarEventResponse])
async def list_calendar_events(
    user_id: Optional[str] = Query(None, description="Filter by event owner/user"),
    lead_id: Optional[str] = Query(None, description="Filter by linked lead"),
    contact_id: Optional[str] = Query(None, description="Filter by linked contact"),
    deal_id: Optional[str] = Query(None, description="Filter by linked deal"),
    start_date: Optional[datetime] = Query(None, description="Filter events on or after this ISO datetime"),
    end_date: Optional[datetime] = Query(None, description="Filter events on or before this ISO datetime"),
    search: Optional[str] = Query(None, description="Case-insensitive search across title, description, and location"),
    sort_by: Optional[str] = Query(None, description="Sort field (start_time, end_time, created_at, title)"),
    sort_order: Optional[str] = Query(None, description="Sort direction (asc, desc)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission(Permission.CALENDAR_READ)),
    db: AsyncSession = Depends(get_db),
):
    """List calendar events with date-window and agenda filtering."""
    repo = CalendarEventRepository(db, current_user.organization_id)
    events = await repo.list_all(
        user_id=user_id,
        lead_id=lead_id,
        contact_id=contact_id,
        deal_id=deal_id,
        start_date=start_date,
        end_date=end_date,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    return [_to_event_resp(e) for e in events]


@router.post("", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
async def create_calendar_event(
    req: CalendarEventCreate,
    current_user: User = Depends(require_permission(Permission.CALENDAR_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new calendar event or meeting."""
    if req.user_id is None:
        req.user_id = current_user.id

    repo = CalendarEventRepository(db, current_user.organization_id)
    event = await repo.create(req)
    loaded = await repo.get_by_id(event.id)
    return _to_event_resp(loaded or event)


@router.get("/{event_id}", response_model=CalendarEventResponse)
async def get_calendar_event(
    event_id: str,
    current_user: User = Depends(require_permission(Permission.CALENDAR_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single calendar event by ID."""
    repo = CalendarEventRepository(db, current_user.organization_id)
    event = await repo.get_by_id(event_id)
    if not event:
        raise NotFoundException("Calendar event not found.")
    return _to_event_resp(event)


@router.patch("/{event_id}", response_model=CalendarEventResponse)
async def update_calendar_event(
    event_id: str,
    req: CalendarEventUpdate,
    current_user: User = Depends(require_permission(Permission.CALENDAR_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    """Update a calendar event."""
    repo = CalendarEventRepository(db, current_user.organization_id)
    event = await repo.get_by_id(event_id)
    if not event:
        raise NotFoundException("Calendar event not found.")
    updated = await repo.update(event, req)
    loaded = await repo.get_by_id(updated.id)
    return _to_event_resp(loaded or updated)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar_event(
    event_id: str,
    current_user: User = Depends(require_permission(Permission.CALENDAR_DELETE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a calendar event."""
    repo = CalendarEventRepository(db, current_user.organization_id)
    event = await repo.get_by_id(event_id)
    if not event:
        raise NotFoundException("Calendar event not found.")
    await repo.delete(event)
