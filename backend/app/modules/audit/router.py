from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.core.permissions import Permission
from app.modules.audit.models import AuditLog
from app.modules.audit.repository import AuditLogRepository
from app.modules.audit.schemas import AuditLogResponse
from app.modules.auth.dependencies import require_permission
from app.modules.users.models import User

router = APIRouter(prefix="/audit", tags=["Audit Logs"])


def _to_audit_resp(log: AuditLog) -> AuditLogResponse:
    resp = AuditLogResponse.model_validate(log)
    if log.user:
        name = f"{log.user.first_name or ''} {log.user.last_name or ''}".strip()
        resp.user_name = name if name else None
        resp.user_email = log.user.email
    return resp


@router.get("", response_model=List[AuditLogResponse])
async def list_audit_logs(
    user_id: Optional[str] = Query(None, description="Filter by actor user ID"),
    action: Optional[str] = Query(None, description="Filter by audit action"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type (lead, deal, etc.)"),
    entity_id: Optional[str] = Query(None, description="Filter by target entity ID"),
    search: Optional[str] = Query(None, description="Case-insensitive search across action, entity_type, and entity_id"),
    start_date: Optional[datetime] = Query(None, description="Filter events on or after this ISO datetime"),
    end_date: Optional[datetime] = Query(None, description="Filter events on or before this ISO datetime"),
    sort_by: Optional[str] = Query(None, description="Sort field (created_at, action, entity_type)"),
    sort_order: Optional[str] = Query(None, description="Sort direction (asc, desc)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission(Permission.AUDIT_READ)),
    db: AsyncSession = Depends(get_db),
):
    """List organization audit logs with advanced filtering, search, sorting, and pagination."""
    repo = AuditLogRepository(db, current_user.organization_id)
    logs = await repo.list_all(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        search=search,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    return [_to_audit_resp(l) for l in logs]


@router.get("/{audit_id}", response_model=AuditLogResponse)
async def get_audit_log(
    audit_id: str,
    current_user: User = Depends(require_permission(Permission.AUDIT_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single audit log entry by ID, strictly organization-scoped."""
    repo = AuditLogRepository(db, current_user.organization_id)
    log_entry = await repo.get_by_id(audit_id)
    if not log_entry:
        raise NotFoundException("Audit log not found.")
    return _to_audit_resp(log_entry)
