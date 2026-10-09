from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.permissions import Permission
from app.modules.auth.dependencies import get_current_user, require_permission
from app.modules.tasks.models import Task, TaskStatus
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import TaskCreate, TaskResponse, TaskSummaryMetrics, TaskUpdate
from app.modules.users.models import User

router = APIRouter(prefix="/tasks", tags=["Tasks & Follow-ups"])


def _to_task_resp(t: Task) -> TaskResponse:
    now = datetime.now(timezone.utc)
    resp = TaskResponse.model_validate(t)
    due_dt = t.due_date if t.due_date.tzinfo else t.due_date.replace(tzinfo=timezone.utc)
    resp.is_overdue = (due_dt < now and t.status != TaskStatus.COMPLETED.value)
    resp.extra_metadata = t.extra_metadata or {}
    if t.assigned_to:
        resp.assigned_to_name = t.assigned_to.full_name
    if t.lead:
        resp.lead_title = t.lead.title
    if t.contact:
        resp.contact_name = t.contact.full_name
    if t.deal:
        resp.deal_title = t.deal.title
    return resp


@router.get("/metrics", response_model=TaskSummaryMetrics)
async def get_task_metrics(
    current_user: User = Depends(require_permission(Permission.TASKS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve follow-up task counts (overdue, due today, upcoming)."""
    repo = TaskRepository(db, current_user.organization_id)
    return await repo.get_metrics()


@router.post("/escalate-overdue")
async def trigger_task_escalation(
    current_user: User = Depends(require_permission(Permission.TASKS_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    """Scan and escalate all tasks overdue by >24 hours to URGENT priority."""
    from app.modules.automation.workflows import escalate_overdue_tasks
    escalated = await escalate_overdue_tasks(db, current_user.organization_id)
    return {
        "success": True,
        "escalated_count": len(escalated),
        "tasks": [_to_task_resp(t) for t in escalated],
    }


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status (PENDING, COMPLETED, etc.)"),
    priority: Optional[str] = Query(None, description="Filter by priority (LOW, MEDIUM, HIGH, URGENT)"),
    assigned_to_id: Optional[str] = Query(None, description="Filter by assigned user"),
    lead_id: Optional[str] = Query(None, description="Filter by lead"),
    contact_id: Optional[str] = Query(None, description="Filter by contact"),
    deal_id: Optional[str] = Query(None, description="Filter by deal"),
    filter_type: Optional[str] = Query(None, description="Filter by overdue, today, or upcoming"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission(Permission.TASKS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """List tasks and follow-ups with filter presets."""
    repo = TaskRepository(db, current_user.organization_id)
    tasks = await repo.list_all(
        status=status,
        priority=priority,
        assigned_to_id=assigned_to_id,
        lead_id=lead_id,
        contact_id=contact_id,
        deal_id=deal_id,
        filter_type=filter_type,
        limit=limit,
        offset=offset,
    )
    return [_to_task_resp(t) for t in tasks]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    req: TaskCreate,
    current_user: User = Depends(require_permission(Permission.TASKS_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new task or follow-up action."""
    repo = TaskRepository(db, current_user.organization_id)
    task = await repo.create(req, created_by_id=current_user.id)
    loaded = await repo.get_by_id(task.id)
    return _to_task_resp(loaded or task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    req: TaskUpdate,
    current_user: User = Depends(require_permission(Permission.TASKS_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    """Update task status, priority, due date, or complete follow-up."""
    repo = TaskRepository(db, current_user.organization_id)
    task = await repo.get_by_id(task_id)
    if not task:
        raise NotFoundException("Task not found.")
    updated = await repo.update(task, req)
    loaded = await repo.get_by_id(updated.id)
    return _to_task_resp(loaded or updated)


@router.post("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: str,
    current_user: User = Depends(require_permission(Permission.TASKS_UPDATE)),
    db: AsyncSession = Depends(get_db),
):
    """Quick 1-click completion for a follow-up task."""
    repo = TaskRepository(db, current_user.organization_id)
    task = await repo.get_by_id(task_id)
    if not task:
        raise NotFoundException("Task not found.")
    updated = await repo.update(task, TaskUpdate(status=TaskStatus.COMPLETED, completed_at=datetime.now(timezone.utc)))
    loaded = await repo.get_by_id(updated.id)
    return _to_task_resp(loaded or updated)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    current_user: User = Depends(require_permission(Permission.TASKS_DELETE)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a task."""
    repo = TaskRepository(db, current_user.organization_id)
    task = await repo.get_by_id(task_id)
    if not task:
        raise NotFoundException("Task not found.")
    await repo.delete(task)
